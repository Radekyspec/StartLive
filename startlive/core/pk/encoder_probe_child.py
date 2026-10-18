"""Minimal one-shot encoder probe subprocess. Never launch a GUI here.

Invoke using `python -m startlive.core.pk.encoder_probe_child <codec>` or
`StartLive[.exe] --pk-encoder-probe <codec>` in a compiled deployment. The
parent process enforces the timeout and cancels/kills an unresponsive probe.
"""

import json
import os
from pathlib import Path

from startlive.core.constant.pk_encoder import (
    ENCODERS, PROBE_DIAGNOSTIC_ENV, PROBE_DIAGNOSTIC_MAX_CHARS,
)


def _write_failure(reason, detail):
    """Best effort, bounded IPC for source and console-less compiled children."""
    destination = os.environ.get(PROBE_DIAGNOSTIC_ENV)
    if not destination:
        return
    result = {"reason": reason[:PROBE_DIAGNOSTIC_MAX_CHARS],
              "detail": detail[:PROBE_DIAGNOSTIC_MAX_CHARS]}
    try:
        # Parent reads only after process exit, so partial writes after a
        # native crash are handled as a missing/invalid diagnostic there.
        Path(destination).write_text(json.dumps(result, ensure_ascii=True),
                                     encoding="utf-8")
    except OSError:
        pass


def probe_main(argv=None):
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {choice.name for choice in ENCODERS}:
        return 2
    # Probing is best-effort and must not starve OBS or the Qt render loop.
    if os.name != "nt":
        try:
            os.nice(10)
        except OSError:
            pass
    try:
        # Keep PyAV, aiortc, and GPU/driver initialization inside this process.
        from .video_encoder_backend import probe_encoder
        if probe_encoder(args[0]):
            return 0
        _write_failure("probe-returned-false", "Encoder probe returned false")
        return 1
    except Exception as error:
        _write_failure(type(error).__name__, str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(probe_main())
