"""RTC admission, media notifications and resource retirement for one session."""
from concurrent.futures import CancelledError
from dataclasses import replace

from startlive.core.constant.pk import NativeInteractionState, PkPhase, PkMode
from startlive.core.constant.pk_session import RtcMediaStage
from startlive.core.exceptions import PkError
from startlive.core.exceptions import TaskCancelled
from startlive.core.pk.peers import PkPeerRegistry, default_media_preference
from startlive.core.pk.publication import publication_channels
from startlive.core.pk.room_info import PkRoomInfoSession
from startlive.core.pk.states.mute import RtcMuteState, RtcMuteUpdate
from startlive.core.pk.states.peers import PkInteractionScope, RtcPublication, \
    RtcUserEvent
from startlive.core.pk.states.room_info import RtcBusinessMessage
from startlive.core.workers.pk.publication_ready import PkPublicationReadyWorker
from .pk_presenter import PkPresenter
from .room_info_controller import PkRoomInfoController


class PkRtcLifecycle:
    def __init__(self, session, connector_factory, worker_factory):
        self.session = session
        self.connector_factory, self.worker_factory = connector_factory, worker_factory
        self.worker = self.future = self.event = self.room = self.peers = None
        self.selected = None
        self.publisher_ready = False
        self.mute_states = {media: RtcMuteState() for media in
                            ("audio", "video")}
        self.generation = 0
        self.notice_generation = None
        self._failure_reported = False
        self.business_mute = None

    def connect(self, ticket, event):
        session = self.session
        session._trace("session.rtc.connect.requested",
                       event_biz_session_id=event.biz_session_id,
                       event_rtc_channel_id=event.rtc_channel_id)
        if session.closed or session.stopping:
            raise PkError("PK 会话正在关闭")
        if session.invitation_only:
            invite = session.invitations.accepted
            if invite is None:
                raise PkError("尚未接受视频 PK 邀请")
            if ((
                    invite.biz_session_id and invite.biz_session_id != event.biz_session_id)
                    # A real source7 invitation can carry "0" before Handle
                    # allocates the RTC channel. Keep the business-session
                    # guard, and compare only an assigned invitation channel.
                    or (invite.rtc_channel_id not in (None, "", "0")
                        and invite.rtc_channel_id != event.rtc_channel_id)):
                raise PkError("视频连线与已接受的邀请不符")
        publication = publication_channels(event)
        business_controls = session.options.mode in (PkMode.TRADITIONAL,
                                                     PkMode.VIDEO_LINK,
                                                     PkMode.VIDEO)
        if event.biz_label == "classic_pk":
            if publication.video or not publication.audio:
                raise PkError("经典 PK JOIN 不是音频发布模式")
            session.view.prepare_classic_audio()
        if business_controls:
            muted = getattr(session.view, "_publisher_mute_states", {}).get(
                "audio", RtcMuteState())
            self.mute_states["audio"] = replace(muted, pending=False)
        # Construct admission resources before installing the new JOIN context.
        # A local startup failure must not leave a room/session behind while
        # PkJoinController clears its key.
        peers = PkPeerRegistry(ticket.uid,
                               PkInteractionScope(event.biz_session_id,
                                                  event.rtc_channel_id),
                               rtc_preference=default_media_preference(
                                   event.default_sub_mode)
                               if business_controls and session.options.mode != PkMode.VIDEO else None)
        room = PkRoomInfoController(session.manager, session.identity,
                                    PkRoomInfoSession(event),
                                    changed=self.room_changed,
                                    polling_stopped=lambda: None,
                                    failed=session._fatal,
                                    identity_guard=session.identity_guard,
                                    poll_interval=2 if business_controls else None,
                                    snapshot_guard=(
                                        lambda: self.business_mute.snapshot_guard())
                                    if business_controls else None,
                                    clock=session._clock)
        previous = (self.event, session.round_state.biz_session_id, self.peers,
                    self.room)
        self.generation += 1
        generation = self.generation
        self._failure_reported = False
        try:
            worker = self.worker_factory(PkPresenter(finished=lambda: None,
                                                     progress=lambda
                                                         value: self.progress(
                                                         value) if (
                                                             worker is self.worker and generation == self.generation
                                                             and self.future is not None and not self.future.done()) else None,
                                                     failed=lambda
                                                         error: self._worker_failed(
                                                         worker, error)),
                                         session.identity,
                                         lambda: self.connector_factory(ticket),
                                         session.view.publish_buffer,
                                         session.view.remote_buffer,
                                         publication=publication,
                                         identity_guard=session.identity_guard,
                                         **({
                                                "audio_muted": True} if business_controls and
                                                                        self.mute_states[
                                                                            "audio"].local_muted else {}))
            self.event = event
            session.round_state.biz_session_id = event.biz_session_id
            self.peers, self.room, self.worker = peers, room, worker
            if business_controls:
                from .mute_controller import PkMuteController
                self.business_mute = PkMuteController(self)
            self.future = session.manager.submit(worker, on_progress=True)
        except Exception:
            room.close()
            self.generation += 1
            self.worker = self.future = None
            self.event, session.round_state.biz_session_id, self.peers, self.room = previous
            raise
        session.join.native_state = NativeInteractionState.WAITING_JOIN
        if session.flow.phase in (PkPhase.MATCHING, PkPhase.INVITING,
                                  PkPhase.STOPPING):
            session.flow.handoff()
        session.view.set_connection_active(True)
        session._trace("session.rtc.worker_started", generation=generation,
                       publish_audio=publication.audio,
                       publish_video=publication.video)
        session._status(
            "正在建立经典 PK 语音…" if event.biz_label == "classic_pk" else "正在建立视频连线…")

    def _worker_failed(self, worker, error):
        # Future completion and the GUI dispatcher callback can arrive in either
        # order. Report once, and never let a retired worker close its successor.
        if worker is not self.worker or self.session.closed or self._failure_reported:
            return
        self._failure_reported = True
        if self.session.stopping and self.business_mute is not None:
            # The requested local teardown still completes when Leave fails.
            # In classic PK this must not retire the independent round owner.
            self.session._error(error)
            return
        self.session._fatal(error)

    def progress(self, event):
        session = self.session
        if session.closed or session.stopping:
            return
        try:
            session.identity_guard(session.identity)
            if isinstance(event, RtcMediaStage):
                session._trace("session.rtc.stage", stage=event,
                               generation=self.generation)
            elif isinstance(event, RtcUserEvent):
                session._trace("session.rtc.user_event", event_kind=event.kind,
                               peer_search=event.uid)
            elif isinstance(event, RtcMuteUpdate):
                if (
                        self.business_mute is not None and event.request_id is not None
                        and event.request_id != self.business_mute.local_revision):
                    return
                session._trace("session.rtc.mute_update", media=event.media,
                               state=event.state,
                               error=str(event.error) if event.error else None)
            if event in (RtcMediaStage.JOINED, RtcMediaStage.CONNECTED):
                session.join.native_state = NativeInteractionState.CONNECTING
                if session.options.mode == PkMode.VIDEO_LINK:
                    self.notify_publication_ready(joined=True)
            elif event == RtcMediaStage.PUBLISHED:
                self.publisher_ready = True
                publication = publication_channels(self.event)
                session.view.set_publisher_available(audio=publication.audio,
                                                     video=publication.video)
                self.room.published()
                if session.options.mode == PkMode.VIDEO:
                    self.notify_publication_ready()
                if self.business_mute is not None:
                    self.business_mute.apply_controls()
            elif isinstance(event, RtcMuteUpdate):
                self.mute_states[event.media] = event.state
                session.view.set_publisher_mute_state(event.media, event.state)
                if event.error:
                    session._error(event.error)
            elif event == RtcMediaStage.SUBSCRIBED:
                if self.selected and not (
                        self.selected.video or self.selected.audio):
                    session._status("已连接，未开启对方画面或声音")
            elif event == RtcMediaStage.MEDIA_READY:
                if self.business_mute is not None:
                    self.business_mute.initialize()
                if self.selected and (
                        self.selected.video or self.selected.audio):
                    received = (
                        "画面和声音" if self.selected.video and self.selected.audio
                        else "画面" if self.selected.video else "声音")
                    session._status("已收到对方" + received)
            elif isinstance(event, RtcBusinessMessage):
                self.room.receive_rtc(event)
            elif isinstance(event, RtcUserEvent):
                if event.kind == "published":
                    stream = event.stream
                    self.subscribe(self.peers.on_publication(
                        RtcPublication(event.uid, stream.video, stream.audio),
                        scope=self.peers.scope,
                        native_state=session.join.native_state))
                elif event.kind in ("unpublished",
                                    "left") and self.selected and event.uid == self.selected.uid:
                    # Retire this local two-party output rather than playing a
                    # stale peer. Exact native Unsub/republication is pending.
                    session._status("对方媒体已离开，正在关闭本地连线")
                    self.stop()
        except Exception as error:
            session._trace("session.rtc.notification.failed", response=event,
                           error_type=type(error).__name__, error=str(error))
            session._fatal(error)

    def notify_publication_ready(self, *, joined=False):
        # main3e0dc0 successful Pub -> UniversalInfo -> Handle4 for business2,
        # retained for existing video PK. Video-link uses completed JoinChannel.
        session = self.session
        generation = self.generation
        if (session.closed or session.stopping or self.event is None
                or (not joined and not self.publisher_ready) or int(
                    session.kind) == 14
                or self.notice_generation == generation):
            return
        self.notice_generation = generation

        def current():
            return not session.closed and not session.stopping and generation == self.generation

        def failed(error, response=None):
            if current():
                # Native action4 failure notifies observers without tearing
                # down the published connection or retrying admission.
                session._trace("session.publication.notice_failed",
                               operation="handle",
                               request=worker.fields if worker is not None else None,
                               response=response,
                               error_type=type(error).__name__,
                               error=str(error))

        def loaded(result):
            if not current():
                return
            try:
                session.identity_guard(session.identity)
                session._trace("session.publication.notice_completed",
                               contains_join=result.join_event is not None)
                if result.join_event is not None:
                    session.join.handle(result.join_event)
            except Exception as error:
                failed(error, response=result.response)

        session._trace("session.publication.notice_requested",
                       generation=generation,
                       action=4, action_type=0, source=0)
        worker = None
        try:
            worker = PkPublicationReadyWorker(
                PkPresenter(finished=loaded, failed=failed), session.identity)
            worker.request_allowed = current
            session.manager.submit(worker)
        except Exception as error:
            failed(error)

    def room_changed(self, info, *, apply_controls=True):
        session = self.session
        if session.closed or session.stopping:
            return
        remote = [member for member in info.members if
                  member.uid != session.identity.uid]
        if len(remote) > 1:
            raise PkError("当前界面仅支持双方视频 PK")
        for member in remote:
            if session.expected_peer_uid is not None and member.uid != session.expected_peer_uid:
                raise PkError("连线房间返回的对手与本次邀请不符")
            self.subscribe(
                self.peers.add_member(member, scope=self.peers.scope))
        # Display identity comes from the same verified business membership
        # used for subscription, never from the first RTC notification.
        session.presentation.peer_uid = remote[0].uid if remote else None
        session._trace("session.room.accepted", version=info.version,
                       interact_channel_id=info.context.interact_channel_id,
                       member_uids=[member.uid for member in info.members],
                       verified_peer_uid=session.presentation.peer_uid,
                       expected_peer_uid=session.expected_peer_uid)
        session.presentation.render()
        if self.business_mute is not None and apply_controls:
            self.business_mute.receive(info.raw.get("stream_control", {}))

    def subscribe(self, desired):
        session = self.session
        if desired is not None:
            if self.selected is not None and self.selected.uid != desired.uid:
                raise PkError("本期仅支持一名 RTC 对端")
            if self.business_mute is not None and self.business_mute.initialized:
                return  # User receive controls own updates after initial subscription.
            session._trace("session.peer.subscribe", peer_search=desired.uid,
                           audio=desired.audio, video=desired.video)
            self.worker.subscribe(desired)
            self.selected = desired

    def set_muted(self, media, muted):
        """Explicit PK control; OBS capture and business HTTP Mute are separate."""
        session = self.session
        # Preserve the pre-existing video-PK publisher control through its
        # RTC path. It must not produce the unsupported HTTP ct=2/mct=1.
        if self.business_mute is not None and not (
                session.options.mode == PkMode.VIDEO and media == "video"):
            return self.business_mute.local(media, muted)
        session._trace("session.mute.requested", media=media, muted=muted)
        if media not in self.mute_states or type(muted) is not bool:
            raise PkError("请选择要静音的声音或画面")
        session.identity_guard(session.identity)
        if session.closed or session.stopping or not self.publisher_ready or self.worker is None:
            raise PkError("视频 PK 发布尚未就绪")
        if not getattr(publication_channels(self.event), media):
            raise PkError("本次视频 PK 未发布此类媒体")
        state = self.mute_states[media]
        if state.pending:
            raise PkError("正在更新静音状态")
        self.worker.set_muted(media, muted)
        self.mute_states[media] = replace(state, requested=muted, pending=True)
        session.view.set_publisher_mute_state(media, self.mute_states[media])

    def stop(self):
        session = self.session
        if self.worker is not None and not session.stopping:
            session._trace("session.rtc.stop_requested",
                           generation=self.generation)
            # Retire HTTP reconciliation while this media owner exits; push
            # round updates are replayed only after local cleanup completes.
            if self.event.biz_label == "classic_pk" and session.round.polling:
                session._exit_query_resume_pending = True
            session.round.stop_polling()
            self.publisher_ready = False
            session.view.set_publisher_available(audio=False, video=False)
            session.view.set_connection_active(False)
            self.generation += 1
            session.stopping = True
            session.join.native_state = NativeInteractionState.STOPPING
            self.room.close()
            if self.business_mute is not None:
                self.business_mute.close()
            if self.event.biz_label == "classic_pk":
                session.view.stop_classic_audio()
            self.worker.stop()

    def stream_control(self, event):
        if (self.business_mute is None or self.event is None
                or self.session.closed or self.session.stopping):
            return
        channel_matches = bool(
            event.rtc_channel_id) and event.rtc_channel_id == self.event.rtc_channel_id
        session_matches = bool(
            event.biz_session_id) and event.biz_session_id == self.event.biz_session_id
        if (not (channel_matches or session_matches)
                or event.uid not in (None, self.event.uid)):
            return
        self.business_mute.receive(event.stream_control, raw_event=event.raw)

    def finish_if_done(self):
        session = self.session
        if self.future is None or not self.future.done():
            return False
        try:
            error = self.future.exception()
        except CancelledError:
            error = None
        if error is not None and not isinstance(error, TaskCancelled):
            self._worker_failed(self.worker, error)
        # Spontaneous completion needs the same retirement as an explicit stop.
        # Keep the stopping gate until the owner has replayed buffered events.
        if not session.stopping and session.round.polling:
            session._exit_query_resume_pending = True
        session.stopping = True
        session.round.stop_polling()
        if session.handle is not None:
            session.handle.retire()
        if self.business_mute is not None:
            self.business_mute.close()
            self.business_mute = None
        if self.event is not None and self.event.biz_label == "classic_pk":
            session.view.stop_classic_audio()
        if self.room is not None:
            self.room.close()
        session._trace("session.rtc.cleanup_completed",
                       generation=self.generation,
                       buffered_events=len(session._pending_round_events))
        self.generation += 1
        self.future = self.worker = None
        session.join.clear()
        self.event = None
        if self.peers is not None:
            self.peers.clear()
        self.peers = self.room = None
        self.selected = None
        if session.options.mode == PkMode.VIDEO_LINK:
            session.round_state.quit_round()
            session._pending_round_events.clear()
            session._exit_query_resume_pending = False
            session.flow.retire()
        session.presentation.peer_uid = None
        self.publisher_ready = False
        self.mute_states = {media: RtcMuteState() for media in
                            ("audio", "video")}
        session.view.set_publisher_available(audio=False, video=False)
        session.view.set_connection_active(False)
        return True
