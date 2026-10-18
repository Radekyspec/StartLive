"""Offline RTC self-test for the actual executable produced by packaging."""
import asyncio
import json

from aiortc import RTCConfiguration, RTCPeerConnection

from .rtc_diagnostics import runtime_details
from .rtc_dtls import configure_pk_dtls, observe_pk_dtls
from .rtc_relay import create_turn_ssl_context
from .trace import rtc_loop_exception_handler


async def probe_connection():
    sender = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    receiver = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    completed = asyncio.get_running_loop().create_future()

    def failed(error):
        if not completed.done():
            completed.set_exception(error)

    try:
        configure_pk_dtls(sender)
        channel = sender.createDataChannel("startlive-rtc-self-test")
        observe_pk_dtls(sender, failed)

        @channel.on("open")
        def opened():
            channel.send(b"startlive-rtc-self-test")

        @channel.on("message")
        def received(data):
            if data == b"startlive-rtc-self-test" and not completed.done():
                completed.set_result(None)

        @receiver.on("datachannel")
        def incoming(remote):
            remote.on("message", lambda data: remote.send(data))

        # No TURN/STUN servers, credentials or business RPCs. Both peers are
        # local; this checks the compiled SSL adapter and actual encrypted I/O.
        async with asyncio.timeout(10):
            await sender.setLocalDescription(await sender.createOffer())
            await receiver.setRemoteDescription(sender.localDescription)
            await receiver.setLocalDescription(await receiver.createAnswer())
            await sender.setRemoteDescription(receiver.localDescription)
            await completed
        return {"ice": sender.iceConnectionState,
                "dtls": sender.sctp.transport.state,
                "data_channel": channel.readyState}
    finally:
        # Close both ends together so shutdown cannot await the still-open peer.
        await asyncio.wait_for(asyncio.gather(sender.close(), receiver.close()),
                               5)
        if completed.done() and not completed.cancelled():
            completed.exception()


def probe_main():
    print(json.dumps(runtime_details(), ensure_ascii=False), flush=True)
    try:
        context = create_turn_ssl_context()
        roots = context.cert_store_stats()["x509_ca"]
        if not roots:
            raise RuntimeError("TURN TLS CA store is empty")
        with asyncio.Runner() as runner:
            runner.get_loop().set_exception_handler(rtc_loop_exception_handler)
            result = runner.run(probe_connection())
        print(json.dumps({"rtc_self_test": "passed", "tls_ca_count": roots,
                          **result}), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({"rtc_self_test": "failed",
                          "error_type": type(error).__name__,
                          "error": str(error)}), flush=True)
        return 1
