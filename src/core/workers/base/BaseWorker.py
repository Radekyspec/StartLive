from typing import Optional, Callable, Union

from requests import Session

from src.core.app_state import create_session
from src.core.constant import HeadersType
from src.core.exceptions.WorkerException import WorkerException
from . import Presenter


class BaseWorker:
    _session: Optional[Session]
    name: str

    def __init__(self, /, name: str, *, with_session: bool = True,
                 headers_type: HeadersType = HeadersType.APP,
                 presenter: Optional[Union[Presenter, list[Presenter]]] = None):
        super().__init__()
        self.name = name
        if isinstance(presenter, list):
            self._presenters = presenter[:]
        elif presenter is not None:
            self._presenters = [presenter]
        else:
            self._presenters = []
        if with_session:
            self._session = create_session(headers_type)
        else:
            self._session = None

    def start(self, report_progress: Callable | None, *args, **kwargs):
        try:
            return self.run(report_progress, *args, **kwargs)
        finally:
            if self._session is not None:
                self._session.close()

    def run(self, report_progress: Callable | None, *args, **kwargs):
        """
        Executes the main operation of the method. This implementation must be overridden
        by subclasses to define specific logic. The function optionally accepts a
        callback for reporting progress as well as additional arguments and keyword
        arguments.

        :param report_progress: Callable function to report progress, if provided.
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        :return: No return value, as this method is not implemented and is expected
            to be overridden.
        """
        raise NotImplementedError

    def add_presenter(self, presenter: Presenter) -> None:
        self._presenters.append(presenter)

    def on_exception(self, exception: Exception, /):
        """
        Handles exceptions by invoking a presenter if it is available.

        This method is used to handle exceptions and delegate the failure handling
        to a presenter, if configured.

        :param exception: The exception that was raised during the operation.
        :type exception: Exception
        """
        if self._presenters:
            wrapped_exception = WorkerException(self.name, exception)
            [p.prepare_fail_view(wrapped_exception) for p in self._presenters]

    def on_finished(self, *args, **kwargs):
        """
        Called when the operation has finished. This method is responsible for triggering
        any necessary final actions by invoking the appropriate presenter methods, if
        available.

        The presenter, if present, prepares the success view by processing the provided
        arguments, allowing for actions to be performed after the operation's completion.

        :param args: Positional arguments that will be passed to the presenter.
        :type args: tuple
        :param kwargs: Keyword arguments that will be passed to the presenter.
        :type kwargs: dict
        """
        if self._presenters:
            [p.prepare_success_view(*args, **kwargs) for p in self._presenters]

    def on_progress(self, *args, **kwargs):
        if self._presenters:
            [p.prepare_progress_view(*args, **kwargs) for p in self._presenters]
