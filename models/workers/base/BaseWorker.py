from typing import Optional, Callable

from PySide6.QtCore import QRunnable, QObject, Signal
from requests import Session

from app_state import create_session


class BaseWorker(QRunnable):
    class Signals(QObject):
        finished = Signal()
        exception = Signal(Exception)

    _session: Optional[Session]
    name: str
    finished: bool
    exception: Optional[Exception]
    signals: Signals

    def __init__(self, name: str, *, with_session: bool = True):
        super().__init__()
        self.name = name
        self.finished = False
        self.exception = None
        self.signals = self.Signals()
        self.setAutoDelete(True)
        if with_session:
            self._session = create_session()
        else:
            self._session = None

    def on_exception(self, *args, **kwargs):
        """
        Handles an exception for the method or operation that has been implemented. It
        serves as a placeholder that requires concrete behavior in derived classes or
        implementations. This method must be overridden with proper exception handling
        logic where applicable.

        :param args: Positional arguments passed to the function.
                     These arguments are user-defined and unspecified per the
                     method signature.
        :param kwargs: Keyword arguments passed to the function.
                       These arguments are user-defined and unspecified as per
                       the method signature.
        :return: No return value; this method is expected to be redefined in a
                 subclass or specific implementation.
        :raises NotImplementedError: Always raised to signal the requirement
                                      for a concrete implementation.
        """
        raise NotImplementedError

    @staticmethod
    def run_wrapper(func: Callable):

        def wrapped(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except Exception as e:
                self.signals.exception.emit(e)
            finally:
                self.signals.finished.emit()

        return wrapped

    def on_finished(self, *args, **kwargs):
        """
        Handles the finalization or cleanup processes after a specific event or task
        has been completed. This method is expected to be overridden by derived
        classes to provide the desired behavior for post-completion operations.

        IMPORTANT: This method WILL BE CALLED regardless of whether the worker's execution succeeded or failed.
        So any exception handling should be handled in the `on_exception` method,
        and any result processing should be handled inside the `run` method.

        :param args: Positional arguments that may be used during the finishing process.
        :type args: Tuple
        :param kwargs: Keyword arguments that may be used during the finishing process.
        :type kwargs: Dict
        :return: None
        :raises NotImplementedError: Always raised to indicate the necessity of
            overriding this method in a derived class.
        """
        raise NotImplementedError
