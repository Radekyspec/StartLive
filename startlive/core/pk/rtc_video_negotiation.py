"""Publication state shared by H.264 and AV1, using aiortc's SDP model.

Only local, aiortc-generated offers are serialized here. Raw server fragments
still use rtc_sdp's lossless merger to retain platform-specific attributes.
"""
from __future__ import annotations

from copy import deepcopy

from aiortc import RTCSessionDescription
from aiortc.sdp import SessionDescription

from startlive.core.exceptions import PkProtocolError


def publication_offer(offer, publishers):
    """Preserve confirmed PT/RTX and fmtp on subsequent Pub/Sub offers."""
    if not publishers:
        return offer
    description = SessionDescription.parse(offer.sdp)
    for transceiver, publication in publishers.items():
        index = transceiver._get_mline_index()
        if index is None or index >= len(description.media) or \
                description.media[index].kind != "video":
            raise PkProtocolError("RTC 发布视频轨道与本地 offer 不一致")
        codecs = deepcopy(publication.codecs or transceiver._codecs)
        if not codecs or codecs[0].mimeType.lower() != publication.mime_type:
            raise PkProtocolError("RTC 发布 offer 缺少请求的视频格式")
        # createOffer resets _codecs to the catalogue even for active senders.
        # Restore both the transceiver and the SDP before setLocalDescription.
        transceiver._codecs = codecs
        media = description.media[index]
        media.rtp.codecs = codecs
        media.fmt = [codec.payloadType for codec in codecs]
    return RTCSessionDescription(str(description), offer.type)


def bind_publication_answer(answer, publishers):
    """Bind the actual server response before SRD can start RTP senders."""
    if publishers:
        media_by_mid = {m.rtp.muxId: m for m in
                        SessionDescription.parse(answer).media}
        for transceiver, publication in publishers.items():
            publication.bind(media_by_mid.get(transceiver.mid), transceiver)
