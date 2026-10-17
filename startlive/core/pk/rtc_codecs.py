"""PK codec preferences: selectable AV1 publishing, H.264 reception and Opus.

H.264 retains the recovered 42001f seed. AV1 publishing is implemented by the
connection-scoped catalogue; it is never advertised to aiortc's stock receiver.
Raw server answers are validated before either video encoder starts sending.
"""
from copy import deepcopy
from types import FunctionType, MethodType

from aiortc import RTCPeerConnection, RTCRtpSender
from aiortc.codecs import CODECS
from aiortc.rtcrtpparameters import RTCRtpCodecCapability, RTCRtpCodecParameters

from startlive.core.exceptions import PkError, PkProtocolError
from .rtc_av1 import source_capability


def set_native_codec_preferences(transceiver, video_config=None):
    if (transceiver.kind == "video" and video_config is not None
            and video_config.codec_family == "av1"):
        set_av1_preferences(transceiver)
        return
    codecs = RTCRtpSender.getCapabilities(transceiver.kind).codecs
    if transceiver.kind == "video":
        selected = [codec for codec in codecs if
                    codec.mimeType.lower() == "video/h264"
                    and codec.parameters.get("profile-level-id") == "42001f"
                    and codec.parameters.get("packetization-mode") == "1"]
    else:
        selected = [codec for codec in codecs if
                    codec.mimeType.lower() == "audio/opus"
                    and codec.clockRate == 48000 and codec.channels == 2]
    if not selected:
        raise PkError("当前媒体组件缺少 PK 所需的 H.264 / Opus 编解码器")
    if transceiver.kind == "video":
        selected.extend(
            codec for codec in codecs if codec.mimeType.lower() == "video/rtx")
    transceiver.setCodecPreferences(selected)


def av1_codecs():
    # Dynamic PTs are local offer choices, not native/server constants.
    feedback = deepcopy(next(c.rtcpFeedback for c in CODECS["video"]
                             if c.mimeType.lower() == "video/h264"))
    return [RTCRtpCodecParameters(mimeType="video/AV1", clockRate=90000,
                                  payloadType=103,
                                  parameters=source_capability().parameters,
                                  rtcpFeedback=feedback),
            RTCRtpCodecParameters(mimeType="video/rtx", clockRate=90000,
                                  payloadType=104, parameters={"apt": 103})]


def enable_av1_publication(pc):
    """Give only this PC's offer/answer methods an extended codec catalogue.

    aiortc 1.15 hardcodes its module-level CODECS in these two methods. Rebind
    their globals on this instance rather than mutate that process-wide table
    across awaits, or copy and maintain the whole peer-connection implementation.
    Receive transceivers still select only the built-in H.264 decoder.
    """
    if not isinstance(pc, RTCPeerConnection) or getattr(pc, "_pk_av1_enabled",
                                                        False):
        return
    catalogue = deepcopy(CODECS)
    catalogue["video"].extend(av1_codecs())
    for name in ("createOffer", "setRemoteDescription"):
        original = getattr(RTCPeerConnection, name)
        scope = dict(original.__globals__, CODECS=catalogue)
        method = FunctionType(original.__code__, scope, original.__name__,
                              original.__defaults__, original.__closure__)
        method.__kwdefaults__ = original.__kwdefaults__
        setattr(pc, name, MethodType(method, pc))
    pc._pk_av1_enabled = True


def set_av1_preferences(transceiver):
    if transceiver.direction != "sendonly":
        raise PkProtocolError("AV1 目前仅用于本地视频发送")
    # The public setter validates against aiortc's global, H.264-only catalogue.
    # These preferences belong to the connection's extended catalogue above.
    transceiver._preferred_codecs = [
        RTCRtpCodecCapability(mimeType=c.mimeType, clockRate=c.clockRate,
                              parameters=c.parameters if c.mimeType == "video/AV1" else {})
        for c in av1_codecs()]
