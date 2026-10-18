"""Video publication state and validated negotiation result."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from aiortc.rtcpeerconnection import find_common_codecs

from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.trace import pk_trace

if TYPE_CHECKING:
    from aiortc.rtcrtpparameters import RTCRtpCodecParameters
    from startlive.core.pk.states.h264 import H264Limits
    from startlive.core.pk.states.av1 import Av1Limits
    from startlive.core.pk.states.encoder import VideoEncodingConfig


@dataclass
class VideoPublication:
    """Own the raw-answer decision; do not attach codec state to library objects."""

    capability: H264Limits | Av1Limits
    config: VideoEncodingConfig
    limits: H264Limits | Av1Limits | None = field(default=None, init=False)
    codecs: list[RTCRtpCodecParameters] = field(default_factory=list,
                                                init=False)

    @property
    def mime_type(self):
        return "video/" + self.config.codec_family

    def bind(self, media, transceiver):
        directions = ("recvonly",) if self.mime_type == "video/av1" else (
            "recvonly", "sendrecv")
        if (media is None or media.kind != "video" or media.port == 0
                or (media.direction or "sendrecv") not in directions):
            raise PkProtocolError("服务端未接受本机视频发布")
        selected = [c for c in media.rtp.codecs if
                    c.mimeType.lower() != "video/rtx"]
        if (len(selected) != 1 or selected[0].mimeType.lower() != self.mime_type
                or selected[0].clockRate != 90000):
            raise PkProtocolError(
                "服务端未选择请求的视频编码格式或 RTP 时钟无效")
        codec = selected[0]
        if self.mime_type == "video/av1":
            from startlive.core.pk.rtc_av1 import encoding_plan, \
                negotiated_limits
            limits = negotiated_limits(self.capability, codec.parameters)
            encoding_plan(self.config, limits)
            encoder_parameters = limits.parameters
            extensions = {}
        else:
            from startlive.core.pk.rtc_h264 import negotiated_limits
            limits, extensions = negotiated_limits(self.capability,
                                                   codec.parameters)
            encoder_parameters = {"profile-level-id": limits.profile_level_id}
        # Let aiortc intersect feedback and match RTX to primary codecs.
        # Its H.264 matcher retains local fmtp, so apply our validated limits.
        codecs = find_common_codecs(transceiver._codecs, media.rtp.codecs)
        if not codecs or codecs[0].mimeType.lower() != self.mime_type:
            raise PkProtocolError("服务端视频格式与本机 offer 不兼容")
        codecs[0].parameters.update(encoder_parameters)
        if self.codecs:
            # aiortc's active sender does not reapply send parameters. Check
            # the full result, including RTX/PT and RTCP feedback, before SRD
            # can install a different routing configuration on the connection.
            if self.limits != limits or self.codecs != codecs:
                raise PkProtocolError(
                    "服务端更改了已发布的视频参数，需要重新连接")
            return
        transceiver.sender.track.bind_video(limits)
        # aiortc owns/releases the encoder on stop. Publication state must not
        # retain a hardware context after the library retires its RTP sender.
        transceiver.sender._RTCRtpSender__encoder.bind_video(limits)
        self.limits, self.codecs = limits, codecs
        pk_trace("rtc.video.negotiated", mid=transceiver.mid,
                 codec=self.config.codec_family,
                 peer_parameters=dict(codec.parameters),
                 encoder_parameters=encoder_parameters,
                 limits=asdict(limits), max_bitrate=limits.max_bitrate,
                 extensions_not_used=extensions)

    def sender_parameters(self, parameters):
        if not self.codecs:
            raise PkProtocolError("视频发送器尚未绑定服务端协商结果")
        if (not parameters.codecs or parameters.codecs[
            0].mimeType.lower() != self.mime_type
                or parameters.codecs[0].payloadType != self.codecs[
                    0].payloadType):
            raise PkProtocolError("视频发送格式与服务端选择不一致")
        parameters = deepcopy(parameters)
        parameters.codecs = deepcopy(self.codecs)
        return parameters
