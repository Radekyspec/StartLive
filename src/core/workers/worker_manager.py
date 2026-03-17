from concurrent.futures import ThreadPoolExecutor
from os import cpu_count
from typing import Callable

from src.core.workers.base import BaseWorker
from .dispatcher import Dispatcher


class WorkerManager:
    _dispatcher: Dispatcher
    _executor: ThreadPoolExecutor

    def __init__(self, dispatcher: Dispatcher, max_workers: int = cpu_count()):
        self._dispatcher = dispatcher
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, worker: BaseWorker, on_finished: Callable | None = None,
               on_exception: Callable | None = None):
        future = self._executor.submit(worker.run)

        def done_callback(fut):
            def finalize():
                exc = fut.exception()
                if exc is not None:
                    if on_exception is not None:
                        on_exception(exc)
                    return

                result = fut.result()
                if on_finished is not None:
                    on_finished(result)

            self._dispatcher.post(finalize)

        future.add_done_callback(done_callback)
        return future
