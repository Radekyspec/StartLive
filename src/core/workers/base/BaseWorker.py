from typing import Optional, Callable

from requests import Session

from src.core.app_state import create_session
from src.core.constant import HeadersType


class BaseWorker:
    _session: Optional[Session]
    name: str

    def __init__(self, *, name: str, /, with_session: bool = True,
                 headers_type: HeadersType = HeadersType.APP,
                 on_exception: Optional[Callable] = None,
                 on_finished: Optional[Callable] = None):
        super().__init__()
        self.name = name
        self._on_exception = on_exception
        self._on_finished = on_finished
        if with_session:
            self._session = create_session(headers_type)
        else:
            self._session = None

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

    def on_exception(self, *args, **kwargs):
        """
        Handles an exception by invoking a predefined callback, if set.

        This method is designed to trigger a callback function provided in advance
        whenever an exception occurs. It passes any provided arguments and keyword
        arguments to the callback function.

        :param args: Positional arguments to pass to the exception callback.
        :type args: tuple
        :param kwargs: Keyword arguments to pass to the exception callback.
        :type kwargs: dict
        :return: None
        """
        if self._on_exception is not None:
            self._on_exception(*args, **kwargs)

    def on_finished(self, *args, **kwargs):
        """
        Executes the `on_finished` callback if it is defined. This method checks whether
        the `_on_finished` callable is not `None` and then invokes it with the provided
        arguments and keyword arguments.

        :param args: Positional arguments passed to the `on_finished` callback.
        :param kwargs: Keyword arguments passed to the `on_finished` callback.
        :return: None
        """
        if self._on_finished is not None:
            self._on_finished(*args, **kwargs)
