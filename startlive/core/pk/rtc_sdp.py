"""Native MID filtering and response-fragment reconciliation.

The rules follow actual-DLL vectors from contract-7. Keep SDP as text so that
codec, transport and extension attributes survive parsing unchanged. Build a
fresh result and never commit a partially reconciled remote description.
"""
from dataclasses import replace
import re

from startlive.core.pk.states.sdp import RtcSdpMedia
from startlive.core.constant.pk_sdp import SDP_DIRECTIONS, SDP_DIRECTION_PAIRS, \
    SDP_SIMULCAST_RE
from startlive.core.exceptions import PkProtocolError


def _clean(text: str) -> str:
    return "".join(line + "\r\n" for line in re.split(r"[\r\n]+", text) if line)


def parse_sdp(text: str) -> tuple[str, list[RtcSdpMedia]]:
    """Split a full description or a headerless media fragment without loss."""
    if not isinstance(text, str):
        raise PkProtocolError("RTC 媒体描述无效")
    header, groups = [], []
    for line in re.split(r"[\r\n]+", text):
        if not line:
            continue
        if line.startswith("m="):
            groups.append([])
        (groups[-1] if groups else header).append(line)
    media = []
    for lines in groups:
        media.append(RtcSdpMedia(
            "\r\n".join(lines) + "\r\n",
            next((line[6:] for line in lines if line.startswith("a=mid:")), ""),
            lines[0][2:].split(" ", 1)[0],
            next((line[2:] for line in lines if line in SDP_DIRECTIONS), ""),
        ))
    return "".join(line + "\r\n" for line in header), media


def _bundle(header: str, media: list[RtcSdpMedia]) -> str:
    mids = " ".join(part.mid for part in media if part.direction != "inactive")
    return re.sub(r"([\r\n]*a=group:BUNDLE)(?: [^\r\n]*)?",
                  lambda match: match[1] + " " + mids, header, count=1)


def local_media_fragment(sdp: str, mids: list[str]) -> str:
    header, media = parse_sdp(sdp)
    selected = set(mids)
    media = [part for part in media if part.mid in selected]
    if len(media) != len(selected):
        raise PkProtocolError("RTC 本地媒体描述缺少需要发布或订阅的轨道")
    # A confirmed pub_status0 keeps the session header and empty BUNDLE,
    # excluding application/media from the RPC fragment, not from the PC.
    return _clean(_bundle(header, media) + "".join(part.text for part in media))


def _adapt_simulcast(remote: str, local: str) -> str:
    source = SDP_SIMULCAST_RE.search(local)
    if source is None:
        return remote
    direction = "send" if source[2] == "recv" else "recv"
    target = SDP_SIMULCAST_RE.search(remote)
    if target:
        return remote[:target.start(2)] + direction + source[3] + remote[
            target.end(3):]
    return remote + "\r\n" + source[1] + direction + source[3]


def _fallback(local: RtcSdpMedia) -> RtcSdpMedia:
    text = local.text
    direction = {"sendonly": "recvonly", "sendrecv": "recvonly",
                 "recvonly": "inactive"}.get(local.direction, local.direction)
    if direction != local.direction:
        if direction == "inactive":
            text = re.sub(r"^(m=[^ ]+ )\d+( [^\r\n]+)", r"\g<1>0\2", text,
                          count=1)
            text = re.sub(r"[\r\n]*a=ssrc:[^\r\n]+", "", text)
            text = re.sub(r"[\r\n]*a=ssrc-group:[^\r\n]+", "", text)
        text = re.sub(r"\n*a=(sendrecv|sendonly|recvonly|inactive)",
                      "\na=" + direction, text, count=1)
    if "\na=setup:actpass" in text:
        text = text.replace("\na=setup:actpass", "\na=setup:active", 1)
    elif "\na=setup:passive" in text or "\na=setup:active" in text:
        # Native execution throws for these unmatched synthetic sections too.
        raise PkProtocolError("RTC 缺失媒体回答，无法确认其 DTLS 角色")
    return replace(local, text=_adapt_simulcast(text, local.text),
                   direction=direction)


def merge_remote_fragment(cached_remote: str, local_sdp: str,
                          fragment: str | None) -> str:
    """Append active media, reconcile by local MID/direction, return full answer."""
    header, pool = parse_sdp(cached_remote)
    if not header or not pool:
        raise PkProtocolError("RTC 缺少初次连接的远端媒体描述")
    if fragment is not None:
        _, incoming = parse_sdp(fragment)
        pool.extend(part for part in incoming
                    if part.kind in ("audio",
                                     "video") and part.direction != "inactive")
    _, local = parse_sdp(local_sdp)
    output = []
    for offer in local:
        index = next((i for i, part in enumerate(pool)
                      if part.mid == offer.mid and (offer.direction,
                                                    part.direction) in SDP_DIRECTION_PAIRS),
                     None)
        if index is None:
            output.append(_fallback(offer))
        else:
            part = pool.pop(index)
            output.append(
                replace(part, text=_adapt_simulcast(part.text, offer.text)))
    if any(part.kind in ("audio", "video") and part.direction != "inactive" for
           part in pool):
        raise PkProtocolError("RTC 回答的媒体轨道与本地协商不一致")
    return _clean(
        _bundle(header, output) + "".join(part.text for part in output))
