import asyncio
from queue import Empty, Full, Queue

from startlive.core.constant.pk_session import RtcMediaStage
from startlive.core.exceptions import PkError
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.room_info import business_message
from startlive.core.pk.states.mute import RtcMuteRequest, RtcMuteUpdate
from startlive.core.pk.states.peers import RtcSubscription
from startlive.core.workers.base import LongLiveWorker


class RtcMediaWorker(LongLiveWorker):
    """One PC/loop. The owner selects a peer from scoped SDK publication.

    Queued messages retain owned bytes (contract25). No inferred Unpub/Unsub.
    Contract38 controller returns are not connectivity evidence. CONNECTED
    follows channel/Join/Members completion; MEDIA_READY follows received
    frames for enabled subscription kinds, not peer receipt of our publication.
    """

    def __init__(self, presenter, identity, ticket, local_buffer,
                 remote_buffer, /,
                 *, publication, audio_muted=False):
        super().__init__(name="视频 PK 音视频", presenter=presenter,
                         with_session=False)
        self.identity, self.ticket = identity, ticket
        self.local_buffer, self.remote_buffer = local_buffer, remote_buffer
        self.publication = publication
        self.audio_muted = audio_muted
        self._commands = Queue(maxsize=32)
        self._mute_commands = Queue(maxsize=8)
        self._closing = False

    def subscribe(self, subscription: RtcSubscription):
        try:
            self._commands.put_nowait(subscription)
        except Full:
            raise PkError("RTC 订阅请求积压，无法继续连线") from None

    def set_muted(self, media, muted, *, signal=True, request_id=None):
        """GUI-safe submission; tracks and signaling stay on the worker loop."""
        if self._closing or not self.is_running:
            raise PkError("RTC 会话已结束")
        try:
            self._mute_commands.put_nowait(
                RtcMuteRequest(media, muted, signal, request_id))
        except Full:
            raise PkError("静音请求尚未处理完成，请稍后重试") from None

    def _owner_active(self):
        if not self.is_running or self._closing:
            return False
        require_current_identity(self.identity)
        return True

    @staticmethod
    async def _set_muted(media, command, report):
        try:
            state = await media.set_muted(command.media, command.muted,
                                          signal=command.signal,
                                          changed=lambda state: report(
                                              RtcMuteUpdate(command.media,
                                                            state,
                                                            request_id=command.request_id)))
        except Exception as error:
            report(RtcMuteUpdate(command.media, media.mute_state(command.media),
                                 f"{type(error).__name__}: {error}",
                                 request_id=command.request_id))
        else:
            report(RtcMuteUpdate(command.media, state,
                                 request_id=command.request_id))

    def run(self, report_progress, *args, **kwargs):
        require_current_identity(self.identity)
        from startlive.core.pk.trace import rtc_loop_exception_handler

        # This worker owns its event loop. Capture aiortc background failures
        # even when they occur between ICE completion and DTLS.start().
        with asyncio.Runner() as runner:
            runner.get_loop().set_exception_handler(rtc_loop_exception_handler)
            return runner.run(self._run(report_progress))

    async def _run(self, report_progress):
        task = asyncio.create_task(
            self._serve(report_progress))
        try:
            while not task.done() and self.is_running:
                require_current_identity(self.identity)
                await asyncio.sleep(0.05)
            if self.is_running:
                await task
        finally:
            if not task.done() and not self._closing:
                task.cancel()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            if isinstance(result, Exception):
                raise result

    async def _serve(self, report_progress):
        from startlive.core.pk.rtc_connection import RtcConnection
        from startlive.core.pk.rtc_media import RtcMediaSession

        report = report_progress
        connection = None
        try:
            connector = RtcConnection(
                self.ticket, on_joined=lambda: report(RtcMediaStage.JOINED))
            async with connector as connection:
                media = RtcMediaSession(
                    connection, self.local_buffer, self.remote_buffer,
                    owner_active=self._owner_active)
                ready = selected = mute_task = None
                try:
                    report(RtcMediaStage.CONNECTED)
                    if "audio" in self.publication and "video" not in self.publication:
                        # Classic capture starts only after JOIN. Wait for its
                        # first PCM packet without requiring a video encoder.
                        try:
                            async with asyncio.timeout(5):
                                while not self.local_buffer.freshness()[1]:
                                    await asyncio.sleep(0.02)
                        except TimeoutError:
                            raise PkError(
                                "等待经典 PK 音频采集超时，请确认 OBS 的 PK 采集已启动") from None
                    await media.publish(video="video" in self.publication,
                                        audio="audio" in self.publication,
                                        audio_muted=self.audio_muted)
                    report(RtcMediaStage.PUBLISHED)
                    while self.is_running:
                        while not connection.user_events.empty():
                            report(connection.user_events.get_nowait())
                        while not connection.notifications.empty():
                            message = business_message(
                                connection.notifications.get_nowait())
                            if message is not None:
                                report(message)
                        try:
                            desired = self._commands.get_nowait()
                        except Empty:
                            desired = None
                        if desired is not None and desired != selected:
                            if selected is not None:
                                if selected.uid != desired.uid:
                                    raise PkError(
                                        "对方 RTC 身份发生变化，需要重新建立连线")
                                if ready is not None:
                                    ready.cancel()
                                    await asyncio.gather(ready,
                                                         return_exceptions=True)
                                    ready = None
                                await media.update_subscription(desired.uid,
                                                                video=desired.video,
                                                                audio=desired.audio)
                            else:
                                await media.subscribe(desired.uid,
                                                      video=desired.video,
                                                      audio=desired.audio)
                            selected = desired
                            report(RtcMediaStage.SUBSCRIBED)
                            if desired.video or desired.audio:
                                ready = asyncio.create_task(
                                    media.wait_for_media())
                        if ready is not None and ready.done():
                            await ready
                            media.check_connection()
                            report(RtcMediaStage.MEDIA_READY)
                            ready = None
                        if mute_task is not None and mute_task.done():
                            await mute_task
                            mute_task = None
                        if mute_task is None:
                            try:
                                mute_command = self._mute_commands.get_nowait()
                            except Empty:
                                mute_command = None
                            if mute_command is not None:
                                mute_task = asyncio.create_task(
                                    self._set_muted(media, mute_command,
                                                    report))
                        media.check_connection()
                        await asyncio.sleep(0.02)
                finally:
                    # stop() can be observed by the serve loop before the
                    # monitor. Never cancel again inside graceful cleanup.
                    self._closing = True
                    if ready is not None:
                        ready.cancel()
                        await asyncio.gather(ready, return_exceptions=True)
                    if mute_task is not None:
                        mute_task.cancel()
                        await asyncio.gather(mute_task, return_exceptions=True)
                    await media.close()
        finally:
            # Ready is set by the owner only after the future also finishes.
            report(RtcMediaStage.CLOSED)
            if connection is not None and connection.leave_error is not None:
                raise connection.leave_error
