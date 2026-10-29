"""RTC admission, media notifications and resource retirement for one session."""
from dataclasses import replace

from startlive.core.constant.pk import NativeInteractionState, PkPhase, PkMode
from startlive.core.constant.pk_session import RtcMediaStage
from startlive.core.pk.identity import require_current_identity
from startlive.core.exceptions import PkError
from startlive.core.pk.join import prepare_join
from startlive.core.workers.pk.rtc_media import RtcMediaWorker
from startlive.core.pk.peers import PkPeerRegistry, default_media_preference
from startlive.core.pk.states.mute import RtcMuteState, RtcMuteUpdate
from startlive.core.pk.states.peers import RtcUserEvent
from startlive.core.pk.states.room_info import RtcBusinessMessage
from startlive.core.workers.pk.publication_ready import PkPublicationReadyWorker
from startlive.core.workers.base.CallbackPresenter import CallbackPresenter
from startlive.PySide.interface_adapters.pk.rtc_presenter import PkRtcPresenter
from .room_info_controller import PkRoomInfoController


class PkRtcLifecycle:
    def __init__(self, session):
        self.session = session
        self.native_state = NativeInteractionState.READY
        self._join_key = None
        self._retired_channels = set()
        self.publication = frozenset()
        self.worker = self.future = self.event = self.room = self.peers = None
        self.selected = None
        self.publisher_ready = False
        self.mute_states = {media: RtcMuteState() for media in
                            ("audio", "video")}
        self.generation = 0
        self.notice_generation = None
        self.business_mute = None

    def handle_join(self, event):
        session = self.session
        require_current_identity(session.identity)
        admission = prepare_join(
            event, session.identity, current_key=self._join_key,
            retired_channels=self._retired_channels,
            native_state=self.native_state,
            blocked_reason=session._join_block_reason(event))
        if admission is None:
            return False
        ticket, publication = admission
        self._join_key = (event.biz_session_id, event.rtc_channel_id,
                          ticket["uid"], event.join_token)
        try:
            self._connect(ticket, event, publication)
        except Exception:
            self._join_key = None
            raise
        return True

    def _connect(self, ticket, event, publication):
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
        if event.biz_label == "classic_pk":
            if "video" in publication or "audio" not in publication:
                raise PkError("经典 PK JOIN 不是音频发布模式")
            session.view.prepare_classic_audio()
        muted = session.view._publisher_mute_states["audio"]
        self.mute_states["audio"] = replace(muted, pending=False)
        # Construct admission resources before installing the new JOIN context.
        # A local startup failure must not leave a room/session behind while
        # handle_join rolls back its admission key.
        peers = PkPeerRegistry(ticket["uid"],
                               rtc_preference=default_media_preference(
                                   event.default_sub_mode)
                               if session.options.mode != PkMode.VIDEO else None)
        room = PkRoomInfoController(self, event)
        previous = (self.event, session.round_state.biz_session_id, self.peers,
                    self.room)
        self.generation += 1
        generation = self.generation
        try:
            worker = RtcMediaWorker(
                None, session.identity, ticket,
                session.view.publish_buffer, session.view.remote_buffer,
                publication=publication,
                audio_muted=self.mute_states["audio"].local_muted)
            worker.add_presenter(PkRtcPresenter(self, worker, generation))
            self.event = event
            session.round_state.biz_session_id = event.biz_session_id
            self.peers, self.room, self.worker = peers, room, worker
            from .mute_controller import PkMuteController
            self.business_mute = PkMuteController(self)
            self.future = session.manager.submit(worker, on_progress=True)
        except Exception:
            room.close()
            if self.business_mute is not None:
                self.business_mute.close()
                self.business_mute = None
            self.generation += 1
            self.worker = self.future = None
            self.event, session.round_state.biz_session_id, self.peers, self.room = previous
            raise
        self.publication = publication
        self.native_state = NativeInteractionState.WAITING_JOIN
        if session.flow.phase in (PkPhase.MATCHING, PkPhase.INVITING,
                                  PkPhase.STOPPING):
            session.flow.handoff()
        session.view.set_connection_active(True)
        session._trace("session.rtc.worker_started", generation=generation,
                       publish_audio="audio" in publication,
                       publish_video="video" in publication)
        session._status(
            "正在建立经典 PK 语音…" if event.biz_label == "classic_pk" else "正在建立视频连线…")

    def progress(self, event):
        session = self.session
        if session.closed or session.stopping:
            return
        try:
            require_current_identity(session.identity)
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
                self.native_state = NativeInteractionState.CONNECTING
                if session.options.mode == PkMode.VIDEO_LINK:
                    self.notify_publication_ready(joined=True)
            elif event == RtcMediaStage.PUBLISHED:
                self.publisher_ready = True
                publication = self.publication
                session.view.set_publisher_available(audio="audio" in publication,
                                                     video="video" in publication)
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
                    self.subscribe(self.peers.on_publication(
                        event.uid, event.stream,
                        native_state=self.native_state))
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

        def loaded(response, join_event):
            if not current():
                return
            try:
                require_current_identity(session.identity)
                session._trace("session.publication.notice_completed",
                               contains_join=join_event is not None)
                if join_event is not None:
                    self.handle_join(join_event)
            except Exception as error:
                failed(error, response=response)

        session._trace("session.publication.notice_requested",
                       generation=generation,
                       action=4, action_type=0, source=0)
        worker = None
        try:
            worker = PkPublicationReadyWorker(
                CallbackPresenter(finished=loaded, failed=failed), session.identity)
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
            self.subscribe(self.peers.add_member(member))
        # Display identity comes from the same verified business membership
        # used for subscription, never from the first RTC notification.
        session.presentation.peer_uid = remote[0].uid if remote else None
        session._trace("session.room.accepted", version=info.version,
                       interact_channel_id=info.interact_channel_id,
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
        require_current_identity(session.identity)
        if session.closed or session.stopping or not self.publisher_ready or self.worker is None:
            raise PkError("视频 PK 发布尚未就绪")
        if media not in self.publication:
            raise PkError("本次视频 PK 未发布此类媒体")
        state = self.mute_states[media]
        if state.pending:
            raise PkError("正在更新静音状态")
        self.worker.set_muted(media, muted)
        self.mute_states[media] = replace(state, requested=muted, pending=True)
        session.view.set_publisher_mute_state(media, self.mute_states[media])

    def handle_leave(self, event):
        """Validate the server LEAVE and retire its local RTC owner; no HTTP."""
        session = self.session
        if self.event is None:
            return
        if (session.options.mode in (PkMode.TRADITIONAL, PkMode.VIDEO_LINK)
                and event.biz_session_id
                and event.biz_session_id != self.event.biz_session_id):
            return
        # Older captures omit the business label; an explicit mismatch is rejected.
        accepted = (
            self.native_state != NativeInteractionState.READY
            and bool(self.event.rtc_channel_id)
            and event.rtc_channel_id == self.event.rtc_channel_id
            and not (self.event.biz_label and event.biz_label
                     and event.biz_label != self.event.biz_label))
        if accepted:
            # Also retire the local deadline awaiting this server-owned LEAVE.
            session._stop_rtc()
        session._trace(
            "session.leave.decision", accepted=accepted,
            event_rtc_channel_id=event.rtc_channel_id,
            event_biz_label=event.biz_label,
            leave_reason={1: 30, 2: 31, 3: 32}.get(event.close_user_reason, 30)
            if accepted else None)

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
            self.native_state = NativeInteractionState.STOPPING
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

    def finished(self, worker, error=None):
        """The manager delivered a terminal result on the GUI dispatcher."""
        if worker is not self.worker:
            return
        try:
            if error is not None and not self.session.closed:
                if self.session.stopping and self.business_mute is not None:
                    # A Leave failure must not retire the independent classic round.
                    self.session._error(error)
                else:
                    self.session._fatal(error)
        finally:
            self._retire_media()

    def _retire_media(self):
        session = self.session
        # Keep the stopping gate through retirement and buffered-event replay.
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
        if self._join_key is not None:
            self._retired_channels.add(self._join_key[:2])
        self._join_key = None
        self.publication = frozenset()
        self.native_state = NativeInteractionState.READY
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
        session._rtc_finished()
