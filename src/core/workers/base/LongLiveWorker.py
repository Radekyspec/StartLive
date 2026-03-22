from .BaseWorker import BaseWorker
from .CancellationToken import CancellationToken
from ...constant import HeadersType


class LongLiveWorker(BaseWorker):
    _cancel_token: CancellationToken

    def __init__(self, name: str, with_session: bool = True,
                 headers_type: HeadersType = HeadersType.APP, *args, **kwargs):
        super().__init__(name=name, with_session=with_session,
                         headers_type=headers_type, *args, **kwargs)
        self._cancel_token = CancellationToken()

    def stop(self) -> None:
        """
        Stops the ongoing operation by triggering the cancellation token.

        This method is designed to stop the execution of processes controlled by
        the cancellation token. It effectively flags the operation for cancellation.

        :return: None
        """
        self._cancel_token.cancel()

    def raise_if_cancelled(self) -> None:
        """
        Raises an exception if the cancellation token has been triggered.

        This method checks the state of the cancellation token and raises an exception
        if cancellation has been requested. It is used to ensure that operations can
        respond appropriately to cancellation requests.

        :return: None
        :raises TaskCancelled: If the cancellation token has been triggered.
        """
        self._cancel_token.raise_if_cancelled()

    @property
    def is_running(self) -> bool:
        """
        Checks if the worker is currently running.

        This property returns a boolean indicating whether the worker is active and
        has not been signaled for cancellation.

        :return: True if the worker is running, False otherwise.
        :rtype: bool
        """
        return not self._cancel_token

    def add_cancel_callback(self, cb) -> None:
        """
        Binds a callback function to the cancel token.

        This method registers a provided callback to be executed when the cancel token
        triggers cancellation.

        :param cb: The callback function to bind to the cancel token.
        :type cb: Callable
        :return: None
        """
        self._cancel_token.add_cancel_callback(cb)
