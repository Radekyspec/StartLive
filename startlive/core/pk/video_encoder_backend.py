"""Per-PK PyAV encoder creation, detection and H.264 CPU fallback support.

Only advertise an encoder after encoding and decoding actual frames,
including an independently decodable refresh frame.
No global aiortc codec registry or OBS setting is changed.
"""
import json
import sys
from fractions import Fraction
from os import environ, name as os_name, pathsep
from pathlib import Path
from subprocess import DEVNULL, Popen, TimeoutExpired
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic, sleep

from startlive.core.constant.pk_encoder import (
    AMF_PRESETS,
    QSV_PRESETS,
    SVT_PRESETS,
    PROBE_TIMEOUT_SECONDS,
    PROBE_DIAGNOSTIC_ENV,
    PROBE_DIAGNOSTIC_MAX_BYTES,
    PROBE_DIAGNOSTIC_MAX_CHARS,
)
from startlive.core.constant.pk_encoder import ENCODERS_BY_NAME
from startlive.core.exceptions import PkError
from startlive.core.pk.states.encoder import VideoEncodingConfig, \
    translate_preset, platform_candidates
from .trace import pk_trace


def codec_options(name, config, *, level, frame_rate, bitrate_bps):
    """Translate the quality preference while enforcing the fixed CBR policy."""
    kbps = max(config.min_bitrate_kbps, bitrate_bps // 1000)
    level_str = "1b" if level == 9 else f"{level // 10}.{level % 10}"
    preset = translate_preset(name, config.preset)
    if name == "libx264":
        params = ["ref=1", f"bframes={config.max_b_frames}",
                  "repeat-headers=1", "scenecut=0",
                  f"vbv-maxrate={kbps}", f"vbv-bufsize={kbps}",
                  f"aq-mode={1 if config.spatial_aq else 0}", "nal-hrd=cbr"]
        return {"preset": preset, "tune": "zerolatency",
                "level": level_str, "x264-params": ":".join(params)}
    shared = {"bf": str(config.max_b_frames),
              "g": str(frame_rate * config.keyframe_interval),
              "maxrate": str(bitrate_bps), "bufsize": str(bitrate_bps)}
    av1_level = f"{2 + (level >> 2)}.{level & 3}"
    if name == "libsvtav1":
        # Explicit rc=2 selects CBR without passing SVT's separate max-bitrate
        # feature (which requires TPL and is unavailable in low-delay mode).
        # FFmpeg's generic level uses decimal major*10+minor for SVT/QSV.
        return {"preset": SVT_PRESETS[preset],
                "level": av1_level.replace(".", ""),
                "bufsize": str(bitrate_bps), "err_detect": "explode",
                "svtav1-params": "rc=2:rtc=1:pred-struct=1:lookahead=0:irefresh-type=2:aq-mode=2"}
    if name in ("av1_amf", "h264_amf"):
        specific = ({"profile": "main", "level": av1_level, "async_depth": "1",
                     "preanalysis": "0", "header_insertion_mode": "frame",
                     "forced_idr": "1",
                     "aq_mode": "caq" if config.spatial_aq else "none"}
                    if name == "av1_amf" else
                    {"profile": "constrained_baseline", "level": level_str,
                     "header_insertion_mode": "idr"})
        return {**shared, **specific, "quality": AMF_PRESETS[preset],
                "usage": "ultralowlatency", "rc": config.rate_control.lower()}
    if name in ("av1_qsv", "h264_qsv"):
        # maxrate == bit_rate selects CBR. Disable lookahead and reordering;
        # keep sequence headers in-band for independently decodable refreshes.
        specific = ({"profile": "main", "level": av1_level.replace(".", ""),
                     "look_ahead_depth": "0"} if name == "av1_qsv" else
                    {"profile": "baseline", "level": level_str})
        return {**shared, **specific, "preset": QSV_PRESETS[preset],
                "async_depth": "1", "forced_idr": "1"}
    if name in ("av1_nvenc", "h264_nvenc"):
        # AV1 levels are sequence-header indices, not H.264 level_idc.
        specific = ({"level": av1_level, "tier": "0", "timing-info": "0"}
                    if name == "av1_nvenc" else
                    {"profile": "baseline", "level": level_str})
        return {**shared, **specific, "preset": preset,
                "rc": config.rate_control.lower(), "zerolatency": "1",
                # No global_header: NVENC repeats SPS/PPS at each IDR.
                "forced-idr": "1", "tune": "ull", "delay": "0",
                "rc-lookahead": "0",
                "spatial-aq": "1" if config.spatial_aq else "0",
                "multipass": "disabled"}
    if name == "h264_videotoolbox":
        return {**shared, "profile": "baseline", "level": level_str,
                "realtime": "1", "allow_sw": "0",
                "prio_speed": "1" if preset == "performance" else "0",
                "constant_bit_rate": "1"}
    if name == "h264_vaapi":
        # FFmpeg VAAPI: smaller compression_level values favor quality.
        return {**shared, "profile": "constrained_baseline", "level": level_str,
                "compression_level":
                    {"performance": "7", "balanced": "4", "quality": "1"}[
                        preset],
                "rc_mode": config.rate_control}
    raise ValueError("unsupported video encoder")


def make_video_context(name, width, height, fps, bitrate_bps, limits, config,
                       *, use_codec_defaults=False, colorspace=1,
                       color_range=1):
    """CodecContext is entirely owned by one RTP sender.

    System-memory I420 remains the input contract for all backends. A backend that
    requires device frames (commonly VA-API/QSV on some PyAV builds) will fail
    the encoding probe and won't be advertised as usable.
    """
    import av
    context = av.CodecContext.create(name, "w")
    context.width, context.height = width, height
    # Query this FFmpeg build instead of guessing input formats by vendor.
    # Only 8-bit 4:2:0 software frames are provided by the current capture path.
    formats = context.codec.video_formats
    supported = {fmt.name for fmt in formats} if formats is not None else None
    pixel_format = next((fmt for fmt in ("yuv420p", "nv12")
                         if supported is None or fmt in supported), None)
    if pixel_format is None:
        raise PkError(f"{name} requires an unsupported input-frame path: "
                      f"{', '.join(sorted(supported))}")
    context.pix_fmt = pixel_format
    context.colorspace = colorspace
    context.color_range = color_range
    # Fixed session target: native bitrate, maxrate and VBV start together.
    context.bit_rate = bitrate_bps
    context.framerate, context.time_base = Fraction(fps, 1), Fraction(1, fps)
    if config.codec_family == "h264":
        context.profile = "Baseline"
    context.max_b_frames = config.max_b_frames
    context.gop_size = fps * config.keyframe_interval
    context.options = codec_options(name, config, level=limits.level,
                                    frame_rate=fps, bitrate_bps=bitrate_bps)
    if use_codec_defaults and name not in ("libx264", "libsvtav1"):
        # Discovery verifies the protocol contract with backend defaults.
        # A user's quality preset/AQ choice is checked separately
        # by the live sender, not treated as a property of the hardware.
        context.options = {key: value for key, value in context.options.items()
                           if key not in {"preset", "quality", "multipass",
                                          "spatial-aq", "aq_mode", "prio_speed",
                                          "compression_level"}}
    context.open()
    if context.options:
        if name == "libsvtav1":
            context.encode(
                None)  # Retire the opened session before rejecting it.
        raise PkError(
            f"{name} did not accept encoder options: {', '.join(sorted(context.options))}")
    return context


def _av1_probe_stream(payloads):
    """Reassemble our W=1 sender payloads for the discovery decoder only."""
    result, current = bytearray(), bytearray()
    for payload in payloads:
        header = payload[0]
        if (header >> 4) & 3 != 1 or bool(header & 128) != bool(current):
            raise PkError("AV1 probe RTP fragments are discontinuous")
        current.extend(payload[1:])
        if header & 64:
            continue
        header_size = 2 if current[0] & 4 else 1
        result.append(current[0] | 2)
        result.extend(current[1:header_size])
        size = len(current) - header_size
        while size >= 128:
            result.append((size & 127) | 128)
            size >>= 7
        result.append(size)
        result.extend(current[header_size:])
        current.clear()
    if current:
        raise PkError("AV1 probe RTP fragments are incomplete")
    return bytes(result)


def _pace_probe_frame(deadline, interval):
    """Space actual submissions; a late frame starts a new schedule."""
    while True:
        now = monotonic()
        remaining = deadline - now
        if remaining <= 0:
            return now + interval
        sleep(remaining)


def probe_encoder(name):
    """Exercise the live sender contract, including a delayed refresh request.

    Never count a CPU fallback or output available only after EOF as hardware
    success. The parent process still bounds native driver initialization.
    """
    import av
    from aiortc.codecs.h264 import H264Encoder, h264_depayload
    from .rtc_video_sender import encoder_delay_budget, PkAv1Encoder, \
        PkH264Encoder
    from .video_encoder_config import configured_plan

    is_av1 = ENCODERS_BY_NAME[name].codec_family == "av1"
    family = "AV1" if is_av1 else "H264"
    encoder_type = PkAv1Encoder if is_av1 else PkH264Encoder

    class ProbeEncoder(encoder_type):
        def _report_runtime(self, backend):
            # Discovery must not import Qt/app state or change the active UI.
            pass

    # H264 retains its bounded discovery workload and backend defaults. AV1
    # must accept the actual fixed resolution/rate policy, including preset/AQ.
    config = (VideoEncodingConfig(encoder=name) if is_av1 else
              VideoEncodingConfig(encoder=name, bitrate_kbps=800, width=320,
                                  height=180))
    limits = encoder_type._source_capability(config.width, config.height)
    plan = configured_plan(config.width, config.height, limits, config)
    encoder = ProbeEncoder(video_config=config, allow_fallback=False,
                           use_codec_defaults=not is_av1)
    encoder.bind_video(limits)

    def make_decoder():
        decoder = av.CodecContext.create("libdav1d" if is_av1 else "h264", "r")
        if is_av1:
            decoder.thread_count = 1
        return decoder

    decoder = make_decoder()
    output_count = 0
    last_timestamp = -1 if is_av1 else None
    refresh_timestamp = None
    interval = 1 / plan.frame_rate
    next_submission = monotonic()
    for index in range(3 * (encoder_delay_budget(plan.frame_rate) + 1)):
        frame = av.VideoFrame(plan.width, plan.height, "yuv420p")
        for plane_index, plane in enumerate(frame.planes):
            luma = 32 + index if is_av1 else 16 + index % 200
            plane.update(
                bytes([luma if plane_index == 0 else 128]) * plane.buffer_size)
        frame.pts, frame.time_base = index, Fraction(1, plan.frame_rate)
        force = output_count >= 2 and refresh_timestamp is None
        if force:
            refresh_timestamp = index * 90000 // plan.frame_rate
        next_submission = _pace_probe_frame(next_submission, interval)
        payloads, timestamp = encoder.encode(frame, force_keyframe=force)
        if not payloads:
            continue
        if last_timestamp is not None and timestamp <= last_timestamp:
            raise PkError(f"{family} probe output timestamps did not advance")
        last_timestamp = timestamp
        output_count += 1
        data = (_av1_probe_stream(payloads) if is_av1 else
                b"".join(h264_depayload(payload) for payload in payloads))
        decoded = decoder.decode(av.Packet(data))
        if len(decoded) != 1 or (decoded[0].width, decoded[0].height) != (
                plan.width, plan.height):
            raise PkError(
                f"{family} probe output cannot be decoded at the requested size")
        if timestamp == refresh_timestamp:
            # The refresh must also be usable by a decoder joining midstream.
            refresh = (bool(payloads[0][0] & 8) if is_av1 else
                       any(nal[0] & 31 == 5 for nal in
                           H264Encoder._split_bitstream(data)))
            fresh = make_decoder().decode(av.Packet(data))
            if (not refresh or len(fresh) != 1
                    or (fresh[0].width, fresh[0].height) != (plan.width,
                                                             plan.height)):
                raise PkError(
                    f"{family} probe refresh cannot be decoded independently")
            return True
    raise PkError(
        f"{family} probe did not complete startup, continuous output and refresh")


# Actual FFmpeg/driver initialization can block while holding the GIL. A
# Python thread is NOT sufficient isolation for the Qt event loop; always
# run probes in a fresh process, which can be killed on timeout/cancellation.

# Cache only completed scans; never publish a partial, cancelled result. The
# lock protects the cache, not the OS subprocess or FFmpeg initialization.
_cache_lock = Lock()
_cached_encoders = None


def probe_process_command(name):
    """Launch a child without Qt; Nuitka's executable cannot accept `-m`.

    Nuitka sets __compiled__ on the entry module rather than sys.frozen. Its
    process_exe points at the unpacked child executable for onefile builds.
    """
    if name not in ENCODERS_BY_NAME:
        raise ValueError("unsupported probe encoder")
    compiled = getattr(sys.modules.get("__main__"), "__compiled__", None)
    if compiled is not None:
        return [getattr(compiled, "process_exe", None) or sys.executable,
                "--pk-encoder-probe", name]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--pk-encoder-probe", name]
    return [sys.executable, "-m", "startlive.core.pk.encoder_probe_child", name]


def _probe_failure(name, status, diagnostic, code=None, error=None):
    """Only the parent writes to the application's configured log."""
    fields = {"backend": name, "status": status, "exit_code": code,
              "reason": status}
    if error is not None:
        fields.update(reason=type(error).__name__,
                      detail=str(error)[:PROBE_DIAGNOSTIC_MAX_CHARS])
    elif status == "failed":
        fields["detail"] = "Probe child exited without a valid diagnostic"
        try:
            with diagnostic.open("rb") as stream:
                raw = stream.read(PROBE_DIAGNOSTIC_MAX_BYTES + 1)
            if len(raw) > PROBE_DIAGNOSTIC_MAX_BYTES:
                raise ValueError("oversized diagnostic")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("invalid diagnostic")
            for key in ("reason", "detail"):
                value = result.get(key)
                if isinstance(value, str):
                    fields[key] = value[:PROBE_DIAGNOSTIC_MAX_CHARS]
        except (OSError, ValueError):
            pass
    elif status == "timeout":
        fields["detail"] = "Probe child exceeded its deadline"
    # Exception text may contain filesystem surrogate escapes. Keep the main
    # UTF-8 file handler writable even when a native error contains them.
    for key in ("reason", "detail"):
        if key in fields:
            fields[key] = fields[key].encode("utf-8", errors="replace").decode(
                "utf-8")
    pk_trace("rtc.video.encoder_probe_failed", **fields)


def probe_encoder_isolated(name, *, timeout=PROBE_TIMEOUT_SECONDS,
                           cancel_event=None):
    """Bounded probe with a private diagnostic file, independent of stdout.

    Exit code 0 alone signals success. The file carries failure details only;
    the parent logs them after reaping the child, then removes the directory.
    """
    command = probe_process_command(name)
    if cancel_event is not None and cancel_event.is_set():
        return "cancelled"
    env = dict(environ)
    if len(command) > 1 and command[1] == "-m":
        project_root = str(Path(__file__).resolve().parents[3])
        previous = environ.get("PYTHONPATH")
        env["PYTHONPATH"] = project_root + (
            pathsep + previous if previous else "")
    try:
        directory = TemporaryDirectory(prefix="startlive-encoder-probe-")
    except OSError as error:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled"
        _probe_failure(name, "start-error", None, error=error)
        return "start-error"
    with directory:
        diagnostic = Path(directory.name) / "failure.json"
        env[PROBE_DIAGNOSTIC_ENV] = str(diagnostic)
        try:
            # No pipes: native driver output cannot fill a pipe or require a
            # console in a Nuitka GUI build. Diagnostics use the private file.
            windows_flags = 0x08000000 | 0x00004000
            proc = Popen(command, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
                         env=env,
                         creationflags=windows_flags if os_name == "nt" else 0)
        except OSError as error:
            if cancel_event is not None and cancel_event.is_set():
                return "cancelled"
            _probe_failure(name, "start-error", diagnostic, error=error)
            return "start-error"
        deadline = monotonic() + max(0.01, timeout)
        status = "failed"
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    status = "cancelled"
                    break
                code = proc.poll()
                if code is not None:
                    status = "ok" if code == 0 else "failed"
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    status = "timeout"
                    break
                pause = min(0.1, remaining)
                if cancel_event is None:
                    sleep(pause)
                else:
                    cancel_event.wait(pause)
        finally:
            if proc.poll() is None:
                proc.kill()
                # Preserve the existing bounded reap even if a driver hangs.
                try:
                    proc.wait(timeout=1)
                except TimeoutExpired:
                    pass
        if status not in ("ok", "cancelled"):
            _probe_failure(name, status, diagnostic, code=proc.returncode)
        return status


def scan_encoders(*, progress=None, cancel_event=None):
    """Bounded isolated scan; `None` means cancelled (not an empty result).

    progress(index, count, choice, status) is called on the CALLER thread;
    Qt clients must transfer it via a thread-safe queue, never touch widgets.
    A successful scan becomes the cache used by an auto-selected RTC sender.
    """
    global _cached_encoders
    choices = platform_candidates()
    available = []
    for index, choice in enumerate(choices, start=1):
        if cancel_event is not None and cancel_event.is_set():
            return None
        if progress is not None:
            progress(index, len(choices), choice, "running")
        status = probe_encoder_isolated(choice.name, cancel_event=cancel_event)
        if status == "cancelled":
            return None
        if status == "ok":
            available.append(choice)
        if progress is not None:
            progress(index, len(choices), choice, status)
    result = tuple(available)
    if cancel_event is not None and cancel_event.is_set():
        return None
    with _cache_lock:
        _cached_encoders = result
    return result


def available_encoders():
    """Cached isolated discovery; safe for RTC worker threads, never GUI."""
    with _cache_lock:
        cached = _cached_encoders
    return cached if cached is not None else scan_encoders()


def encoder_attempts(requested):
    """Try verified auto hardware in order, with CPU as the final candidate."""
    if requested == "auto":
        # Auto retains H.264's negotiated family. AV1 is explicitly selected.
        names = [choice.name for choice in available_encoders() if
                 choice.codec_family == "h264"]
        return tuple(dict.fromkeys([*names, "libx264"]))
    if requested == "libx264" or ENCODERS_BY_NAME[
        requested].codec_family == "av1":
        # Never cross the negotiated codec family or unexpectedly put a
        # hardware sender's workload onto the CPU.
        return (requested,)
    return requested, "libx264"
