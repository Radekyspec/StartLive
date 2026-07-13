from functools import partial

from src.PySide.states import LoginState
from src.core import app_state
from src.core.constant import LoginResult
from src.core.workers.announce import FetchAnnounceWorker
from src.core.workers.area import FetchAreaWorker
from src.core.workers.base import Presenter
from src.core.workers.login import TicketFetchWorker
from src.core.workers.pre_live import FetchRoomStatusWorker, FetchPreLiveWorker


class FetchLoginPresenter(Presenter):
    def __init__(self, view: "MainWindow", state: LoginState):
        super().__init__()
        self._view = view
        self._state = state

    @staticmethod
    def post_login(parent: "MainWindow", state: LoginState):
        if app_state.scan_status["scanned"]:
            fetch_ticket = TicketFetchWorker()
            parent.add_thread(
                fetch_ticket,
                on_finished=fetch_ticket.on_finished,
            )
            fetch_status = FetchRoomStatusWorker()
            parent.add_thread(
                fetch_status,
                on_finished=fetch_status.on_finished
            )
            fetch_prelive = FetchPreLiveWorker()
            parent.add_thread(
                fetch_prelive,
                on_finished=partial(fetch_prelive.on_finished,
                                    parent.panel, state)
            )
            fetch_announce = FetchAnnounceWorker()
            parent.add_thread(
                fetch_announce,
                on_finished=partial(fetch_announce.on_finished,
                                    parent.panel)
            )
            area_worker = FetchAreaWorker(state)
            parent.add_thread(
                area_worker,
                on_finished=area_worker.on_finished
            )

    def prepare_success_view(self, login_result: LoginResult):
        if login_result == LoginResult.CANCELLED:
            return
        self.post_login(self._view, self._state)
        match login_result:
            case LoginResult.SUCCESS:
                self._state.qrScanned.emit()
                fetch_usernames = FetchUsernamesWorker("")
                self._view.add_thread(
                    fetch_usernames,
                    on_finished=fetch_usernames.on_finished
                )
            case LoginResult.QR_EXPIRED:
                self._state.qrExpired.emit()

    def prepare_fail_view(self, *args, **kwargs):
        ...

    def prepare_progress_view(self, res: LoginResult):
        if res != LoginResult.QR_NOT_CONFIRMED:
            return
        self._state.qrNotConfirmed.emit()
