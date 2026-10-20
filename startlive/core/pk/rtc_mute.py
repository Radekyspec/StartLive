"""Contract31/32 ordering for StartLive's explicit PK publication controls."""
import asyncio
from dataclasses import replace

from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.states.mute import RtcMuteState


class RtcPublisherMute:
    """One owning event loop, with explicit readiness and local-gate adapters.

    The provider checks completed publication (including applied SDP),
    current session ownership, joined signaling and usable PC. That publication
    check is stronger StartLive policy: contract33 corrects native engine90c to
    Join callid, not a publication marker. Track presence alone is not readiness.
    Serial execution, retirement and rechecking after a reply are StartLive
    ownership policies, not native timing assertions.

    This explicit PK action does not change OBS sources and does not depend
    on business Mute HTTP acknowledgements or native source observers.
    """

    def __init__(self, signaling, *, ready, apply_local):
        self.signaling, self.ready, self.apply_local = signaling, ready, apply_local
        self._states = {kind: RtcMuteState() for kind in ("audio", "video")}
        self._lock = asyncio.Lock()
        self.closed = False

    def state(self, media):
        return self._states[media]

    def _require_ready(self):
        if self.closed or self.ready() is not True:
            raise PkError("RTC 发布尚未就绪或当前会话已结束")
        self.signaling._require_joined()

    async def set_muted(self, media, muted, *, changed=None, signal=True):
        if media not in self._states or type(muted) is not bool:
            raise PkProtocolError("RTC 静音请求需指定音频或视频及布尔值")
        self._require_ready()
        async with self._lock:
            self._require_ready()
            self._states[media] = replace(self._states[media], requested=muted,
                                          pending=True)
            try:
                if muted:
                    self.apply_local(media, True)
                    self._states[media] = replace(self._states[media],
                                                  local_muted=True)
                if changed is not None:
                    changed(self._states[media])
                if signal:
                    await self.signaling.mute(media, muted)
                self._require_ready()
                if not muted:
                    self.apply_local(media, False)
                self._states[media] = replace(self._states[media],
                                              local_muted=muted,
                                              acknowledged=muted)
            finally:
                # Failed mute retains its local gate. Failed unmute never
                # opens it; neither error schedules a compensating request.
                self._states[media] = replace(self._states[media],
                                              pending=False)
            return self._states[media]

    def close(self):
        self.closed = True
