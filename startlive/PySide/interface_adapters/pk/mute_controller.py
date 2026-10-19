"""Business mute synchronization for one admitted RTC generation."""
from collections import deque
from copy import deepcopy
from dataclasses import replace

from startlive.core.exceptions import PkError
from startlive.core.pk.states.peers import RtcSubscription
from startlive.core.workers.pk.mute import PkMuteWorker
from .pk_presenter import PkPresenter


class PkMuteController:
    def __init__(self, rtc):
        self.rtc = rtc
        self.closed = self.initialized = self.busy = False
        self.queue = deque()
        self.pending = {}
        self.failed_muted = set()
        self.snapshot_epoch = self.local_revision = 0
        self.versions = {"audio": -1, "video": -1}
        for media in self.versions:
            baseline = rtc.event.stream_control.get(media + "_control", {})
            version = baseline.get("version") if isinstance(baseline,
                                                            dict) else None
            if type(version) is int:
                self.versions[media] = version
        self.controls = {}
        self.initial_audio_muted = rtc.mute_states["audio"].local_muted
        self.remote = {"audio": False,
                       "video": rtc.event.biz_label == "classic_pk"}
        self.capabilities = None
        self.unknown_stream_control_raw = None

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
        view = self.rtc.session.view
        if hasattr(view, "set_remote_mute_state"):
            view.set_remote_mute_state(**self.remote)

    @staticmethod
    def _known_shape(controls):
        if not isinstance(controls, dict) or not controls:
            return False
        if set(controls) - {"audio_control", "video_control",
                            "pub_sub_control"}:
            return False
        recognized = False
        for media in ("audio", "video"):
            if media + "_control" not in controls:
                continue
            control = controls[media + "_control"]
            if not isinstance(control, dict) or type(
                    control.get("version")) is not int:
                return False
            if set(control) - {"version", "operator_uid", "mute_local_mode",
                               "mute_remote_uids"}:
                return False
            if not ({"mute_local_mode", "mute_remote_uids"} & control.keys()):
                return False
            if "mute_local_mode" in control:
                mode = control["mute_local_mode"]
                if type(mode) is not int or mode not in (0, 1):
                    return False
            if "mute_remote_uids" in control:
                remotes = control["mute_remote_uids"]
                if remotes is not None and (not isinstance(remotes, list) or
                                            any(type(uid) is not int for uid in
                                                remotes)):
                    return False
            recognized = True
        return recognized

    def receive(self, controls, *, raw_event=None):
        if self.closed:
            return
        if (raw_event is not None and self.unknown_stream_control_raw is None
                and not self._known_shape(controls)):
            self.unknown_stream_control_raw = deepcopy(raw_event)
            self.rtc.session._trace("session.stream_control.unknown_shape",
                                    response=self.unknown_stream_control_raw)
        if not isinstance(controls, dict):
            return
        updated = []
        for media in ("audio", "video"):
            control = controls.get(media + "_control")
            if not isinstance(control, dict):
                continue
            version = control.get("version")
            if type(version) is not int or version <= self.versions[media]:
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
            # Only observed 0/1 modes are interpreted; unknown modes stay raw.
            if (media == "audio" and type(mode) is int and mode in (0, 1)
                    and self.rtc.publisher_ready and self._accept_control(media,
                                                                          False,
                                                                          bool(
                                                                              mode))):
                self.local(media, bool(mode), send=False)
            remotes = control.get("mute_remote_uids")
            if remotes is None:
                remotes = []
            if ("mute_remote_uids" in control
                    and isinstance(remotes, list) and all(
                        type(uid) is int for uid in remotes)
                    and self._accept_control(media, True,
                                             self.capabilities.uid in remotes)):
                self.set_remote(media, self.capabilities.uid in remotes,
                                send=False)

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

    def snapshot_guard(self):
        """A query overlapping a local write cannot undo that write on delivery."""
        epoch = self.snapshot_epoch
        settled = not any(self.pending.values())
        return lambda: not self.closed and settled and epoch == self.snapshot_epoch

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
                PkPresenter(finished=lambda _: done(), failed=done),
                session.identity, self.rtc.event.biz_session_id, target,
                media=media, remote=remote, muted=muted)
            worker.request_allowed = lambda: not self.closed
            session.manager.submit(worker)
        except Exception as error:
            done(error)

    def close(self):
        self.closed = True
        self.queue.clear()
