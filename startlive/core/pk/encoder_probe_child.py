"""Minimal one-shot encoder probe subprocess. Never launch a GUI here.

Invoke using `python -m startlive.core.pk.encoder_probe_child <codec>` or
`StartLive[.exe] --pk-encoder-probe <codec>` in a compiled deployment. The
parent process enforces the timeout and cancels/kills an unresponsive probe.
"""

from startlive.core.constant.pk_encoder import ENCODERS


def probe_main(argv=None):
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {choice.name for choice in ENCODERS}:
        return 2
    # Probing is best-effort and must not starve OBS or the Qt render loop.
    import os
    if os.name != "nt":
        try:
            os.nice(10)
        except OSError:
            pass
    try:
        # Keep PyAV, aiortc, and GPU/driver initialization inside this process.
        from .video_encoder_backend import probe_encoder
        return 0 if probe_encoder(args[0]) else 1
    except Exception as error:
        from .trace import pk_trace
        pk_trace("rtc.video.encoder_probe_failed", backend=args[0],
                 reason=type(error).__name__, detail=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(probe_main())
