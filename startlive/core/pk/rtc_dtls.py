"""Per-connection DTLS cipher compatibility for the aiortc PK provider.

aiortc 1.14 offers only ECDSA-authenticated suites. The native binary includes
ECDHE-RSA suites and cipher policy strings allowing them; an RSA server cannot
negotiate with aiortc's default. Add modern RSA-authenticated suites while keeping
the same client certificate, SRTP profiles and remote fingerprint validation.
"""
from aiortc import RTCPeerConnection
from aiortc.rtcdtlstransport import RTCCertificate

from startlive.core.constant.pk_dtls import PK_DTLS_CIPHERS
from startlive.core.exceptions import PkError
from .trace import pk_trace


class _PkCertificate(RTCCertificate):
    def _create_ssl_context(self, srtp_profiles):
        context = super()._create_ssl_context(srtp_profiles)
        context.set_cipher_list(PK_DTLS_CIPHERS)
        return context


def observe_pk_dtls(peer, on_error):
    """Surface startup exceptions from aiortc's detached connection task.

    SSL context construction precedes the first DTLS statechange event. If it
    raises, aiortc can leave the channel connecting and DTLS in 'new' forever.
    Keep this handler scoped to the initial data transport of this peer.
    """
    if not isinstance(peer, RTCPeerConnection):
        return
    dtls = peer.sctp.transport
    original_start = dtls.start

    async def start(parameters):
        pk_trace("rtc.dtls.start", pc_id=hex(id(peer)), state=dtls.state)
        try:
            await original_start(parameters)
        except Exception as error:
            pk_trace("rtc.dtls.start.failed", pc_id=hex(id(peer)),
                     state=dtls.state, error_type=type(error).__name__,
                     error=str(error))
            # The owner propagates the exception and closes the peer. Consume
            # it here so the detached provider task has no unhandled exception.
            on_error(error)

    dtls.start = start


def configure_pk_dtls(peer):
    """Install before creating any transport, without global provider patches.

    aiortc has no public certificate/cipher configuration on RTCPeerConnection.
    Isolate the private adapter here; reject incompatible layouts explicitly.
    Injected non-aiortc offline peers do not need this provider-specific setup.
    """
    if not isinstance(peer, RTCPeerConnection):
        return
    certificates = getattr(peer, "_RTCPeerConnection__certificates", None)
    if (not isinstance(certificates, list) or len(certificates) != 1
            or not isinstance(certificates[0], RTCCertificate)
            or peer.sctp is not None or peer.getTransceivers()):
        raise PkError("RTC 组件不支持当前 PK 安全连接配置")
    certificate = certificates[0]
    # Retain the original key/certificate; all SDP fingerprints stay identical.
    peer._RTCPeerConnection__certificates = [
        _PkCertificate(certificate._key, certificate._cert)
    ]
