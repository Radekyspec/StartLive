"""Business mute synchronization for one admitted RTC generation."""
from collections import deque
from dataclasses import replace

from startlive.core.exceptions import PkError
from startlive.core.pk.room_info import parse_stream_controls
from startlive.core.pk.states.peers import RtcSubscription
from startlive.core.workers.pk.mute import PkMuteWorker
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter


class PkMuteController:
    def __init__(self, rtc):
        self.rtc = rtc
        self.closed = self.initialized = self.busy = False
        self.queue = deque()
        self.pending = {}
        self.failed_muted = set()
        self.snapshot_epoch = self.local_revision = 0
        baseline, _ = parse_stream_controls(rtc.event.stream_control)
        self.versions = {
            media: baseline[media]["version"] if media in baseline else -1
            for media in ("audio", "video")
        }
        self.controls = {}
        self.initial_audio_muted = rtc.mute_states["audio"].local_muted
        self.remote = {"audio": False,
                       "video": rtc.event.biz_label == "classic_pk"}
        self.capabilities = None
        self._reported_unknown_controls = False

    def initialize(self):
        if self.closed or self.initialized or self.rtc.selected is None:
            return
        self.initialized = True
        self.capabilities = self.rtc.selected
        self._enqueue("audio", False, self.initial_audio_muted)
        self._enqueue("audio", True, False)
        self._enqueue("video", True, self.remote["video"])
        self._render_remote()

    def local(self, media, muted, *, send=True):
        if media != "audio" or type(muted) is not bool:
            raise PkError("业务静音仅支持本端音频")
        rtc = self.rtc
        if self.closed or not rtc.publisher_ready:
            raise PkError("本端音频尚未发布")
        state = rtc.mute_states[media]
        if ((state.requested if state.pending else state.local_muted) == muted
                and (media, False) not in self.failed_muted):
            return
        revision = self.local_revision + 1
        rtc.worker.set_muted(media, muted, signal=False, request_id=revision)
        self.local_revision = revision
        rtc.mute_states[media] = replace(state, requested=muted, pending=True)
        rtc.session.view.set_publisher_mute_state(media, rtc.mute_states[media])
        if send:
            self.initial_audio_muted = muted
            self._enqueue(media, False, muted)

    def set_remote(self, media, muted, *, send=True):
        if self.closed or not self.initialized:
            raise PkError("对方媒体尚未订阅")
        if media not in self.remote or type(muted) is not bool:
            raise PkError("远端静音参数无效")
        if send and media == "video" and self.rtc.event.biz_label == "classic_pk":
            raise PkError("经典 PK 没有对方画面")
        if self.remote[media] == muted and (media,
                                            True) not in self.failed_muted:
            return
        remote = self.remote | {media: muted}
        desired = RtcSubscription(self.capabilities.uid,
                                  audio=self.capabilities.audio and not remote[
                                      "audio"],
                                  video=self.capabilities.video and not remote[
                                      "video"])
        self.rtc.worker.subscribe(desired)
        self.remote = remote
        self.rtc.selected = desired
        self._render_remote()
        if send:
            self._enqueue(media, True, muted)

    def _render_remote(self):
        self.rtc.session.view.set_remote_mute_state(**self.remote)

    def receive(self, controls, *, raw_event=None):
        if self.closed:
            return
        parsed, issues = parse_stream_controls(controls)
        if issues and not self._reported_unknown_controls:
            self._reported_unknown_controls = True
            self.rtc.session._trace(
                "session.stream_control.invalid", details=issues,
                response=raw_event if raw_event is not None else controls)
        updated = []
        for media, control in parsed.items():
            version = control["version"]
            if version <= self.versions[media]:
                continue
            self.versions[media] = version
            self.controls[media] = control
            updated.append(media)
        self.apply_controls(updated)

    def apply_controls(self, updated=None):
        if self.closed or not self.initialized:
            return
        for media, control in self.controls.items():
            if updated is not None and media not in updated:
                continue
            mode = control.get("mute_local_mode")
            if (media == "audio" and mode is not None
                    and self.rtc.publisher_ready
                    and self._accept_control(media, False, mode)):
                self.local(media, mode, send=False)
            if "mute_remote_uids" in control:
                muted = self.capabilities.uid in control["mute_remote_uids"]
                if self._accept_control(media, True, muted):
                    self.set_remote(media, muted, send=False)

    def _accept_control(self, media, remote, muted):
        key = (media, remote)
        if self.pending.get(key) or (key in self.failed_muted and not muted):
            return False
        self.failed_muted.discard(key)
        return True

    def _enqueue(self, media, remote, muted):
        if self.closed:
            return
        rtc = self.rtc
        target = rtc.selected.uid if remote else rtc.session.identity.uid
        key = (media, remote)
        self.failed_muted.discard(key)
        self.pending[key] = self.pending.get(key, 0) + 1
        self.snapshot_epoch += 1
        self.queue.append((media, remote, muted, target))
        self._drain()

    @property
    def snapshot_revision(self):
        """Only settled revisions may apply controls from an HTTP snapshot."""
        return None if self.closed or any(self.pending.values()) else self.snapshot_epoch

    def _drain(self):
        if self.closed or self.busy or not self.queue:
            return
        media, remote, muted, target = self.queue.popleft()
        self.busy = True
        session = self.rtc.session

        def done(error=None):
            self.busy = False
            key = (media, remote)
            self.pending[key] -= 1
            self.snapshot_epoch += 1
            if not self.closed:
                if error is not None:
                    # An HTTP failure must not let an unchanged server
                    # snapshot silently reopen a locally muted track.
                    if muted and not self.pending[key]:
                        self.failed_muted.add(key)
                    session._error(error)
                self._drain()

        try:
            worker = PkMuteWorker(
                CallbackPresenter(finished=lambda _=None: done(), failed=done),
                session.identity, self.rtc.event.biz_session_id, target,
                media=media, remote=remote, muted=muted)
            worker.request_allowed = lambda: not self.closed
            session.manager.submit(worker)
        except Exception as error:
            done(error)

    def close(self):
        self.closed = True
        self.queue.clear()
