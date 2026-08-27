from src.core import app_state
from src.core.constant import LoginResult
from src.core.workers.announce import FetchAnnounceWorker
from src.core.workers.area import FetchAreaWorker
from src.core.workers.base import Presenter
from src.core.workers.login import TicketFetchWorker
from src.core.workers.pre_live import FetchPreLiveWorker, FetchRoomStatusWorker
from src.core.workers.usernames import FetchUsernamesWorker
from src.PySide.interface_adapters import MainWindowView
from src.PySide.interface_adapters.announce import FetchAnnouncePresenter
from src.PySide.interface_adapters.area import FetchAreaPresenter
from src.PySide.interface_adapters.login import TicketFetchPresenter
from src.PySide.interface_adapters.pre_live import FetchPreLivePresenter
from src.PySide.states import LoginState


class FetchLoginPresenter(Presenter):
    def __init__(self, view: MainWindowView, state: LoginState) -> None:
        super().__init__()
        self._view = view
        self._state = state

    @staticmethod
    def post_login(parent: MainWindowView, state: LoginState) -> None:
        if app_state.scan_status["scanned"]:
            panel = parent.require_panel()
            parent.add_thread(TicketFetchWorker(TicketFetchPresenter()))
            parent.add_thread(FetchRoomStatusWorker())
            parent.add_thread(
                FetchPreLiveWorker(FetchPreLivePresenter(panel, state)))
            parent.add_thread(
                FetchAnnounceWorker(FetchAnnouncePresenter(panel)))
            parent.add_thread(
                FetchAreaWorker(FetchAreaPresenter(state)))

    def prepare_success_view(self, login_result: LoginResult) -> None:
        if login_result == LoginResult.CANCELLED:
            return
        self.post_login(self._view, self._state)
        match login_result:
            case LoginResult.SUCCESS:
                self._state.qrScanned.emit()
                self._view.add_thread(FetchUsernamesWorker(""))
            case LoginResult.QR_EXPIRED:
                self._state.qrExpired.emit()

    def prepare_fail_view(self, exception: Exception) -> None:
        ...

    def prepare_progress_view(self, res: LoginResult) -> None:
        if res != LoginResult.QR_NOT_CONFIRMED:
            return
        self._state.qrNotConfirmed.emit()
