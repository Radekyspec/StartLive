"""Connection-local codec negotiation adapted from aiortc 1.15.0.

Only the codec catalogue lookup differs from the upstream methods, besides
explicit private attribute names needed outside RTCPeerConnection's class.
Keep these methods in sync when upgrading aiortc; the source parity test checks
that contract. Ordinary functions work in both CPython and Nuitka builds.

Upstream: https://github.com/aiortc/aiortc/blob/1.15.0/src/aiortc/rtcpeerconnection.py

Copyright (c) Jeremy Lainé.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of aiortc nor the names of its contributors may
      be used to endorse or promote products derived from this software without
      specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
from __future__ import annotations

from aiortc.rtcpeerconnection import (
    HEADER_EXTENSIONS,
    OperationError,
    Optional,
    RTCDtlsTransport,
    RTCIceTransport,
    RTCSessionDescription,
    RTCTrackEvent,
    RemoteStreamTrack,
    add_remote_candidates,
    allocate_mid,
    asyncio,
    clock,
    create_media_description_for_sctp,
    create_media_description_for_transceiver,
    filter_preferred_codecs,
    find_common_codecs,
    find_common_header_extensions,
    reverse_direction,
    sdp,
    wrap_session_description,
)


async def create_offer(self) -> RTCSessionDescription:
    """
    Create an SDP offer for the purpose of starting a new WebRTC
    connection to a remote peer.

    :rtype: :class:`RTCSessionDescription`
    """
    # check state is valid
    self._RTCPeerConnection__assertNotClosed()

    # offer codecs
    for transceiver in self._RTCPeerConnection__transceivers:
        transceiver._codecs = filter_preferred_codecs(
            self._pk_codec_catalogue[transceiver.kind][:],
            transceiver._preferred_codecs
        )
        transceiver._headerExtensions = HEADER_EXTENSIONS[transceiver.kind][:]

    mids = self._RTCPeerConnection__seenMids.copy()

    # create description
    ntp_seconds = clock.current_ntp_time() >> 32
    description = sdp.SessionDescription()
    description.origin = f"- {ntp_seconds} {ntp_seconds} IN IP4 0.0.0.0"
    description.msid_semantic.append(
        sdp.GroupDescription(semantic="WMS", items=["*"])
    )
    description.type = "offer"

    def get_media(
            description: sdp.SessionDescription,
    ) -> list[sdp.MediaDescription]:
        return description.media if description else []

    def get_media_section(
            media: list[sdp.MediaDescription], i: int
    ) -> Optional[sdp.MediaDescription]:
        return media[i] if i < len(media) else None

    # handle existing transceivers / sctp
    local_media = get_media(self._RTCPeerConnection__localDescription())
    remote_media = get_media(self._RTCPeerConnection__remoteDescription())
    for i in range(max(len(local_media), len(remote_media))):
        local_m = get_media_section(local_media, i)
        remote_m = get_media_section(remote_media, i)
        media_kind = local_m.kind if local_m else remote_m.kind
        mid = local_m.rtp.muxId if local_m else remote_m.rtp.muxId
        if media_kind in ["audio", "video"]:
            transceiver = self._RTCPeerConnection__getTransceiverByMid(mid)
            transceiver._set_mline_index(i)
            description.media.append(
                create_media_description_for_transceiver(
                    transceiver,
                    cname=self._RTCPeerConnection__cname,
                    direction=transceiver.direction,
                    mid=mid,
                )
            )
        elif media_kind == "application":
            self._RTCPeerConnection__sctp_mline_index = i
            description.media.append(
                create_media_description_for_sctp(
                    self._RTCPeerConnection__sctp, legacy=self._sctpLegacySdp,
                    mid=mid
                )
            )

    # handle new transceivers / sctp
    def next_mline_index() -> int:
        return len(description.media)

    def add_datachannel_section() -> None:
        self._RTCPeerConnection__sctp_mline_index = next_mline_index()
        description.media.append(
            create_media_description_for_sctp(
                self._RTCPeerConnection__sctp, legacy=self._sctpLegacySdp,
                mid=allocate_mid(mids)
            )
        )

    # JSEP specifies that it should only be added after audio/video m-sections
    # but the `alwaysNegotiateDataChannels` option overrides that:
    # https://w3c.github.io/webrtc-extensions/#always-negotiating-datachannels
    # This implies that it will be used for negotiating BUNDLE.
    if not self._RTCPeerConnection__sctp and self._RTCPeerConnection__configuration.alwaysNegotiateDataChannels:
        self._RTCPeerConnection__createSctpTransport()
        add_datachannel_section()

    for transceiver in filter(
            lambda x: x.mid is None and not x.stopped,
            self._RTCPeerConnection__transceivers
    ):
        transceiver._set_mline_index(next_mline_index())
        description.media.append(
            create_media_description_for_transceiver(
                transceiver,
                cname=self._RTCPeerConnection__cname,
                direction=transceiver.direction,
                mid=allocate_mid(mids),
            )
        )
    if (
            self._RTCPeerConnection__sctp
            and self._RTCPeerConnection__sctp.mid is None
            and not self._RTCPeerConnection__configuration.alwaysNegotiateDataChannels
    ):
        add_datachannel_section()

    bundle = sdp.GroupDescription(semantic="BUNDLE", items=[])
    for media in description.media:
        bundle.items.append(media.rtp.muxId)
    description.group.append(bundle)

    return wrap_session_description(description)


async def set_remote_description(
        self, sessionDescription: RTCSessionDescription
) -> None:
    """
    Changes the remote description associated with the connection.

    :param sessionDescription: An :class:`RTCSessionDescription` created from
                                information received over the signaling channel.
    """
    self._RTCPeerConnection__log_debug(
        "setRemoteDescription(%s)\n%s",
        sessionDescription.type,
        sessionDescription.sdp,
    )

    # parse and validate description
    description = sdp.SessionDescription.parse(sessionDescription.sdp)
    description.type = sessionDescription.type
    self._RTCPeerConnection__validate_description(description, is_local=False)

    # apply description
    iceCandidates: dict[RTCIceTransport, sdp.MediaDescription] = {}
    trackEvents = []
    for i, media in enumerate(description.media):
        dtlsTransport: Optional[RTCDtlsTransport] = None
        self._RTCPeerConnection__seenMids.add(media.rtp.muxId)
        if media.kind in ["audio", "video"]:
            # find transceiver
            transceiver = None
            for t in self._RTCPeerConnection__transceivers:
                if t.kind == media.kind and t.mid in [None, media.rtp.muxId]:
                    transceiver = t
                    break
            if transceiver is None:
                transceiver = self._RTCPeerConnection__createTransceiver(
                    direction="recvonly", kind=media.kind
                )
            if transceiver.mid is None:
                transceiver._set_mid(media.rtp.muxId)
                transceiver._set_mline_index(i)

            # negotiate codecs
            common = filter_preferred_codecs(
                find_common_codecs(self._pk_codec_catalogue[media.kind],
                                   media.rtp.codecs),
                transceiver._preferred_codecs,
            )

            if not len(common):
                raise OperationError(
                    "Failed to set remote {} description send parameters".format(
                        media.kind
                    )
                )

            transceiver._codecs = common
            transceiver._headerExtensions = find_common_header_extensions(
                HEADER_EXTENSIONS[media.kind], media.rtp.headerExtensions
            )

            # configure direction
            direction = reverse_direction(media.direction)
            if description.type in ["answer", "pranswer"]:
                transceiver._setCurrentDirection(direction)
            else:
                transceiver._offerDirection = direction

            # create remote stream track
            if (
                    direction in ["recvonly", "sendrecv"]
                    and not transceiver.receiver.track
            ):
                transceiver.receiver._track = RemoteStreamTrack(
                    kind=media.kind, id=description.webrtc_track_id(media)
                )
                trackEvents.append(
                    RTCTrackEvent(
                        receiver=transceiver.receiver,
                        track=transceiver.receiver.track,
                        transceiver=transceiver,
                    )
                )

            # memorise transport parameters
            dtlsTransport = transceiver.receiver.transport
            self._RTCPeerConnection__remoteDtls[transceiver] = media.dtls
            self._RTCPeerConnection__remoteIce[transceiver] = media.ice

        elif media.kind == "application":
            if not self._RTCPeerConnection__sctp:
                self._RTCPeerConnection__createSctpTransport()
            if self._RTCPeerConnection__sctp.mid is None:
                self._RTCPeerConnection__sctp.mid = media.rtp.muxId
                self._RTCPeerConnection__sctp_mline_index = i

            # configure sctp
            if media.profile == "DTLS/SCTP":
                self._sctpLegacySdp = True
                self._RTCPeerConnection__sctpRemotePort = int(media.fmt[0])
            else:
                self._sctpLegacySdp = False
                self._RTCPeerConnection__sctpRemotePort = media.sctp_port
            self._RTCPeerConnection__sctpRemoteCaps = media.sctpCapabilities

            # memorise transport parameters
            dtlsTransport = self._RTCPeerConnection__sctp.transport
            self._RTCPeerConnection__remoteDtls[
                self._RTCPeerConnection__sctp] = media.dtls
            self._RTCPeerConnection__remoteIce[
                self._RTCPeerConnection__sctp] = media.ice

        if dtlsTransport is not None:
            # add ICE candidates
            iceTransport = dtlsTransport.transport
            iceCandidates[iceTransport] = media

            # set ICE role
            if description.type == "offer" and not iceTransport._role_set:
                iceTransport._connection.ice_controlling = media.ice.iceLite
                iceTransport._role_set = True

            # set DTLS role
            if description.type == "offer" and media.dtls.role == "client":
                dtlsTransport._set_role(role="server")
            if description.type == "answer":
                dtlsTransport._set_role(
                    role="server" if media.dtls.role == "client" else "client"
                )

    # remove bundled transports
    bundle = next((x for x in description.group if x.semantic == "BUNDLE"),
                  None)
    if bundle and bundle.items:
        # find main media stream
        primaryMid = bundle.items[0]
        primaryTransport = None
        for transceiver in self._RTCPeerConnection__transceivers:
            if transceiver.mid == primaryMid:
                primaryTransport = transceiver.receiver.transport
                break
        if self._RTCPeerConnection__sctp and self._RTCPeerConnection__sctp.mid == primaryMid:
            primaryTransport = self._RTCPeerConnection__sctp.transport

        # replace transport for bundled media
        oldTransports = set()
        slaveMids = bundle.items[1:]
        for transceiver in self._RTCPeerConnection__transceivers:
            if transceiver.mid in slaveMids and not transceiver._bundled:
                oldTransports.add(transceiver.receiver.transport)
                transceiver.receiver.setTransport(primaryTransport)
                transceiver.sender.setTransport(primaryTransport)
                transceiver._bundled = True
        if (
                self._RTCPeerConnection__sctp
                and self._RTCPeerConnection__sctp.mid in slaveMids
                and not self._RTCPeerConnection__sctp._bundled
        ):
            oldTransports.add(self._RTCPeerConnection__sctp.transport)
            self._RTCPeerConnection__sctp.setTransport(primaryTransport)
            self._RTCPeerConnection__sctp._bundled = True

        # stop and discard old ICE transports
        for dtlsTransport in oldTransports:
            await dtlsTransport.stop()
            await dtlsTransport.transport.stop()
            self._RTCPeerConnection__dtlsTransports.discard(dtlsTransport)
            self._RTCPeerConnection__iceTransports.discard(
                dtlsTransport.transport)
            iceCandidates.pop(dtlsTransport.transport, None)
        self._RTCPeerConnection__updateIceGatheringState()
        self._RTCPeerConnection__updateIceConnectionState()
        self._RTCPeerConnection__updateConnectionState()

    # add remote candidates
    coros = [
        add_remote_candidates(iceTransport, media)
        for iceTransport, media in iceCandidates.items()
    ]
    await asyncio.gather(*coros)

    # FIXME: in aiortc 2.0.0 emit RTCTrackEvent directly
    for event in trackEvents:
        self.emit("track", event.track)

    # connect
    asyncio.ensure_future(self._RTCPeerConnection__connect())

    # update signaling state
    if description.type == "offer":
        self._RTCPeerConnection__setSignalingState("have-remote-offer")
    elif description.type == "answer":
        self._RTCPeerConnection__setSignalingState("stable")

    # replace description
    if description.type == "answer":
        self._RTCPeerConnection__currentRemoteDescription = description
        self._RTCPeerConnection__pendingRemoteDescription = None
    else:
        self._RTCPeerConnection__pendingRemoteDescription = description
