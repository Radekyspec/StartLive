from src.core.constant import HeadersType
from .BaseWorker import BaseWorker
from .CancellationToken import CancellationToken


class LongLiveWorker(BaseWorker):
    cancel_token: CancellationToken

    def __init__(self, name: str, *, with_session: bool = True,
                 headers_type: HeadersType = HeadersType.APP):
        super().__init__(name, with_session=with_session,
                         headers_type=headers_type)
        self.cancel_token = CancellationToken()

    def stop(self) -> None:
        """
        Stops the ongoing operation by triggering the cancellation token.

        This method is designed to stop the execution of processes controlled by
        the cancellation token. It effectively flags the operation for cancellation.

        :return: None
        """
        self.cancel_token.cancel()

    def add_cancel_callback(self, cb) -> None:
        """
        Binds a callback function to the cancel token.

        This method registers a provided callback to be executed when the cancel token
        triggers cancellation.

        :param cb: The callback function to bind to the cancel token.
        :type cb: Callable
        :return: None
        """
        self.cancel_token.add_cancel_callback(cb)
