"""PK diagnostics in the existing StartLive log, without affecting the flow."""
import json
import logging
from dataclasses import asdict, is_dataclass
from enum import Enum
from threading import Lock

from startlive.core.constant.pk_trace import _DESCRIPTIONS, _OPERATIONS, \
    _REASONS, _RTC_STATES, _RTC_STATE_TYPES
from startlive.core.log import get_logger


# Only results, parsing decisions and failures belong in the normal log.
# UI actions, polling probes, packet counters and most setup steps do
# not become visible just because the application's logger enables DEBUG.
# ICE/DTLS state transitions are sparse and needed to diagnose connection stalls.


class _DtlsFailureHandler(logging.Handler):
    def emit(self, record):
        # aiortc normally hides the reason at DEBUG. Only forward its explicit
        # handshake failure templates; never enable general SDP/packet logging.
        if (isinstance(record.msg, str)
                and record.msg.startswith(
                    "RTCDtlsTransport(%s) x DTLS handshake failed (")):
            try:
                pk_trace("rtc.dtls.failed", detail=record.getMessage())
            except Exception:
                pass
        elif record.msg in (
                "RTCDtlsTransport(%s) - DTLS shutdown by remote party",
                "RTCDtlsTransport(%s) - DTLS shutdown complete",
                "%s Consent to send expired"):
            pk_trace("rtc.transport.closed_reason", detail=record.getMessage())


_dtls_trace_lock = Lock()


def enable_dtls_failure_trace():
    with _dtls_trace_lock:
        for name, level in (("aiortc.rtcdtlstransport", logging.DEBUG),
                            ("aioice.ice", logging.INFO)):
            logger = logging.getLogger(name)
            if not any(isinstance(handler, _DtlsFailureHandler) for handler in
                       logger.handlers):
                logger.addHandler(_DtlsFailureHandler())
            logger.setLevel(level)


def sdp_for_trace(sdp: str) -> str:
    """Retain an outgoing SDP's structure without its ICE credentials."""
    return "".join(line for line in sdp.splitlines(keepends=True)
                   if not line.startswith(("a=ice-pwd:", "a=ice-ufrag:")))


def _json_value(value):
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"hex": bytes(value).hex()}
    return str(value)


def pk_trace(event: str, *, logger_name="PK", **fields):
    """Write readable results with request context and protocol identifiers.

    The user authorized complete PK response diagnostics for account testing.
    This helper neither discovers credentials nor installs another log handler.
    """
    try:
        if event == "rtc.media.stats" and fields.get("stage") != "timeout":
            return
        description = _DESCRIPTIONS.get(event)
        if description is None:
            if event.endswith(
                    (".failed", "_failed", ".error", ".fatal", ".invalid",
                     ".rejected", ".timeout")):
                description = "PK 处理失败" if not event.startswith(
                    "rtc.") else "RTC 音视频处理失败"
            else:
                return
        if event.startswith("http."):
            description = f"{_OPERATIONS.get(fields.get('operation'), 'PK')} {description}"
        if event in ("rtc.pc.state", "rtc.dtls.state", "rtc.channel.state"):
            state = fields.get("state")
            if state in _RTC_STATES:
                fields["state_description"] = _RTC_STATES[state]
            state_type = fields.get("state_type")
            if state_type in _RTC_STATE_TYPES:
                fields["state_type_description"] = _RTC_STATE_TYPES[state_type]
        reason = fields.get("reason")
        if isinstance(reason, str) and reason in _REASONS:
            fields["reason_description"] = _REASONS[reason]
        line = json.dumps(
            {"description": description, "event": event, **fields},
            ensure_ascii=False,
            separators=(",", ":"), default=_json_value)
        get_logger(logger_name).info(line)
    except Exception:
        # Logging/formatting must never change requests, callbacks or cleanup.
        pass
