"""Scoped PK send negotiation; never change aiortc's global codec registry.

RFC 6184 sections 8.1 / 8.2.2:
https://www.rfc-editor.org/rfc/rfc6184.html#section-8.2.2
Level limits are the H264 Annex A Baseline limits (also published in x264's
common/tables.c). Native remote-content filtering preserves present remote
format parameters through encoder configuration, and its x264 factory uses
format.level. The initial offer retains the proven Baseline 3.1 codec seed.
Adapting the sending copy to negotiated limits remains StartLive policy, not
a claim of identical native capture/backend behavior.
"""
import re
from math import isqrt

from aiortc.sdp import H264Profile, parse_h264_profile_level_id

from startlive.core.constant.pk_h264 import H264_LEVELS
from startlive.core.constant.pk_video_config import DEFAULT_VIDEO_CONFIG
from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.states.h264 import H264Limits
from startlive.core.pk.states.video import VideoEncodingPlan


def level_rank(level):
    return 10.5 if level == 9 else level


def level_limits(level):
    if level not in H264_LEVELS:
        raise PkProtocolError("服务端选择了当前 PK 不支持的 H264 level")
    mbps, fs, dpb, bitrate, cpb = H264_LEVELS[level]
    profile = "42100b" if level == 9 else f"4200{level:02x}"
    return H264Limits(level, profile, mbps, fs, dpb, bitrate * 1000, cpb * 1000)


def macroblocks(width, height):
    return ((width + 15) // 16) * ((height + 15) // 16)


def validate_encoder_sps(nal, width, height, frame_rate, limits):
    """Validate actual output against receiver capacity, not vendor defaults.

    RFC 6184 negotiates an upper level. A lower SPS level is valid provided
    the picture also fits its declared level. DPB capacity is in macroblocks;
    the allowed reference count therefore depends on the actual dimensions.
    """
    actual_level, actual_width, actual_height, references = inspect_sps(nal)
    if (actual_width, actual_height) != (width,
                                         height) or width <= 0 or height <= 0:
        raise PkError("H264 SPS dimensions do not match the input picture")
    if level_rank(actual_level) > level_rank(limits.level):
        raise PkError(
            f"H264 SPS level {actual_level} exceeds negotiated level {limits.level}")
    declared = level_limits(actual_level)
    picture_mbs = macroblocks(width, height)
    for bound in (limits, declared):
        if not _geometry_fits(width, height,
                              bound) or picture_mbs * frame_rate > bound.max_mbps:
            raise PkError(
                f"H264 picture size/frame rate exceeds level {bound.level} limits")
    # H.264 Annex A limits DPB frame capacity to 16 even for small pictures.
    reference_limit = min(16, limits.max_dpb // picture_mbs,
                          declared.max_dpb // picture_mbs)
    if references > reference_limit:
        raise PkError(
            f"H264 SPS references {references} exceed DPB capacity {reference_limit}")
    return actual_level, references


def _geometry_fits(width, height, limits):
    mb_width, mb_height = (width + 15) // 16, (height + 15) // 16
    return (mb_width * mb_height <= min(limits.max_fs, limits.max_dpb,
                                        limits.max_mbps)
            and max(mb_width, mb_height) <= isqrt(8 * limits.max_fs))


def source_capability(width, height):
    """Validate capture geometry without raising the initial codec offer."""
    width, height = width // 2 * 2, height // 2 * 2
    if not (2 <= width <= 3840 and 2 <= height <= 2160):
        raise PkError("OBS 视频尺寸超出当前 PK 支持范围")
    # Native codec selection does not prove that capture dimensions may raise
    # the first offer. 42001f was accepted in the real 04:36 publication; the
    # source-derived 420028 offer was rejected at 11:32 (no matched codec).
    # Keep source pixels unchanged here; encoding_plan adapts the sending copy
    # after bind_publication_answer has applied the actual peer limits.
    return level_limits(31)


def encoding_plan(width, height, limits):
    """Keep aspect ratio; only the outgoing copy adapts to negotiated limits."""
    width, height = width // 2 * 2, height // 2 * 2
    if width < 2 or height < 2:
        raise PkError("OBS 视频尺寸无效")
    if not _geometry_fits(width, height, limits):
        source_width, source_height = width, height
        low, high = 1, width // 2
        while low < high:
            half = (low + high + 1) // 2
            candidate_width = half * 2
            candidate_height = max(2,
                                   candidate_width * source_height // source_width // 2 * 2)
            if _geometry_fits(candidate_width, candidate_height, limits):
                low = half
            else:
                high = half - 1
        width = low * 2
        height = max(2, width * source_height // source_width // 2 * 2)
    if not _geometry_fits(width, height, limits):
        raise PkError("服务端 H264 能力无法容纳当前视频")
    fps = min(DEFAULT_VIDEO_CONFIG.frame_rate,
              limits.max_mbps // macroblocks(width, height))
    return VideoEncodingPlan(width, height, fps)


def _profile(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise PkProtocolError("服务端 H264 profile-level-id 无效")
    try:
        profile, level = parse_h264_profile_level_id(value)
    except ValueError:
        raise PkProtocolError("服务端 H264 profile 或 level 不受支持") from None
    level = 9 if int(level) == -1 else int(level)
    level_limits(level)
    return profile, level


def negotiated_limits(offered, parameters):
    remote_profile = str(parameters.get("profile-level-id", "42000a"))
    profile, default_level = _profile(remote_profile)
    if profile != H264Profile.PROFILE_BASELINE:
        raise PkProtocolError("服务端更改了已提供的 H264 Baseline 格式")
    if str(parameters.get("packetization-mode", "0")) != "1":
        raise PkProtocolError("服务端不支持当前 H264 RTP 分片方式")
    asymmetry = str(parameters.get("level-asymmetry-allowed", "0"))
    if asymmetry not in ("0", "1"):
        raise PkProtocolError("服务端 H264 level-asymmetry-allowed 无效")
    if asymmetry == "0" and level_rank(default_level) > level_rank(
            offered.level):
        raise PkProtocolError("服务端在对称 H264 协商中提高了 level")
    receive_level = default_level
    if "max-recv-level" in parameters:
        value = str(parameters["max-recv-level"])
        if not re.fullmatch(r"[0-9a-fA-F]{4}", value):
            raise PkProtocolError("服务端 H264 max-recv-level 无效")
        # RFC 6184: four HEX digits, profile-iop then level-idc, not a decimal level.
        iop, level_idc = int(value[:2], 16), int(value[2:], 16)
        if level_idc == 9 and iop & 16:
            raise PkProtocolError(
                "服务端 H264 max-recv-level 的 level 1b 标记无效")
        receive_level = 9 if level_idc == 9 or (
                level_idc == 11 and iop & 16) else level_idc
        level_limits(receive_level)
        if level_rank(receive_level) <= level_rank(default_level):
            raise PkProtocolError("服务端 H264 max-recv-level 未高于默认 level")
    selected_level = min(offered.level,
                         receive_level if asymmetry == "1" else default_level,
                         key=level_rank)
    selected = level_limits(selected_level)
    # RFC max-* fields are OPTIONAL receive extensions, not permission to stamp
    # a lower SPS level onto larger pictures. Preserve/validate them for logs;
    # this conservative publisher stays inside the selected level's full limits.
    base = level_limits(receive_level)
    floors = {"max-fs": base.max_fs, "max-mbps": base.max_mbps,
              "max-smbps": base.max_mbps, "max-br": base.max_bitrate // 1000,
              "max-cpb": base.max_cpb // 1000}
    extensions = {}
    for name in (*floors, "max-dpb"):
        if name not in parameters:
            continue
        value = str(parameters[name])
        if not re.fullmatch(r"[0-9]+", value) or int(value) < floors.get(name,
                                                                         1):
            raise PkProtocolError(f"服务端 H264 {name} 能力无效")
        extensions[name] = int(value)
    return selected, extensions


def inspect_sps(nal):
    """Read Baseline SPS geometry for validation; never return or log picture bytes."""
    if len(nal) < 4 or nal[0] & 31 != 7 or nal[1] != 66:
        raise PkError("H264 编码器未输出 Baseline SPS")
    profile, level = _profile(nal[1:4].hex())
    if profile not in (H264Profile.PROFILE_BASELINE,
                       H264Profile.PROFILE_CONSTRAINED_BASELINE):
        raise PkError("H264 实际编码 profile 超出协商范围")
    raw = nal[1:].replace(b"\x00\x00\x03", b"\x00\x00")
    offset = 24

    def bits(count):
        nonlocal offset
        if offset + count > len(raw) * 8:
            raise PkError("H264 SPS 不完整")
        value = 0
        for _ in range(count):
            value = (value << 1) | ((raw[offset // 8] >> (7 - offset % 8)) & 1)
            offset += 1
        return value

    def ue():
        zeros = 0
        while bits(1) == 0:
            zeros += 1
            if zeros > 31:
                raise PkError("H264 SPS 数值无效")
        return (1 << zeros) - 1 + bits(zeros)

    ue()  # seq_parameter_set_id
    ue()  # log2_max_frame_num_minus4
    order = ue()
    if order == 0:
        ue()
    elif order == 1:
        bits(1)
        ue()  # signed Exp-Golomb offsets have the same coded length
        ue()
        cycle = ue()
        if cycle > 255:
            raise PkError("H264 SPS picture order 无效")
        for _ in range(cycle):
            ue()
    elif order != 2:
        raise PkError("H264 SPS picture order 无效")
    references = ue()
    bits(1)
    width, height = (ue() + 1) * 16, (ue() + 1) * 16
    if bits(1) != 1:
        raise PkError("PK H264 编码器输出了未协商的隔行视频")
    bits(1)
    if bits(1):
        left, right, top, bottom = ue(), ue(), ue(), ue()
        width -= (left + right) * 2
        height -= (top + bottom) * 2
    return level, width, height, references
