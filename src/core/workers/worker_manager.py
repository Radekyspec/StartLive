from concurrent.futures import ThreadPoolExecutor, Future, CancelledError
from os import cpu_count
from traceback import print_exc
from typing import Any, Callable

from .base import BaseWorker, LongLiveWorker
from .dispatcher import Dispatcher
from ..exceptions import TaskCancelled
from ..log import get_logger


class WorkerManager:
    _dispatcher: Dispatcher
    _executor: ThreadPoolExecutor
    _jobs: dict[Future, BaseWorker]
    _worker_typeset: set[str]

    def __init__(self, dispatcher: Dispatcher,
                 max_workers: int = cpu_count()) -> None:
        self._dispatcher = dispatcher
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="backend-worker",
        )
        self._jobs: dict[Future, BaseWorker] = {}
        self._worker_typeset: set[str] = set()
        self.logger = get_logger(self.__class__.__name__)

    def submit(self, worker: BaseWorker, *,
               on_progress: Callable | None = None) -> Future:
        if (worker_name := worker.__class__.__name__) in self._worker_typeset:
            self.logger.warning(f"Attempting to add {worker_name}"
                                f" but one already exists.")
            return Future()  # return a placeholder future

        future = self._executor.submit(self._run_worker, worker, on_progress)
        self.logger.info(f"{worker_name} added to thread pool")
        self._worker_typeset.add(worker_name)

        self._jobs[future] = worker
        future.add_done_callback(self._handle_done)
        return future

    def _run_worker(self, worker: BaseWorker | LongLiveWorker,
                    on_progress: Callable | None) -> Any:
        if isinstance(worker, LongLiveWorker):
            worker.raise_if_cancelled()

        def report_progress() -> None:
            if on_progress is None:
                return
            self._dispatcher.post(on_progress)

        return worker.run(report_progress=report_progress)

    def cancel(self, job_future: Future) -> bool:
        worker = self._jobs.get(job_future, None)
        if worker is None or not isinstance(worker, LongLiveWorker):
            return False

        worker.stop()
        return job_future.cancel()

    def _handle_done(self, future: Future) -> None:
        worker = self._jobs.pop(future, None)
        if worker is None:
            return

        worker_name = worker.name
        self._worker_typeset.remove(worker_name)

        def finalize() -> None:
            # future canceled before start
            if future.cancelled():
                return

            try:
                result = future.result()
            except (TaskCancelled, CancelledError):
                pass
            except Exception:
                try:
                    worker.on_exception()
                except Exception:
                    print_exc()
            else:
                if result is None:
                    worker.on_finished()
                elif isinstance(result, tuple):
                    worker.on_finished(*result)
                else:
                    worker.on_finished(result)

        self._dispatcher.post(finalize)
        self.logger.info(
            f"{worker_name} removed from thread pool")

    def shutdown(self, cancel_running: bool = True) -> None:
        if cancel_running:
            for job_future in list(self._jobs.keys()):
                self.cancel(job_future)

        self._executor.shutdown(wait=False, cancel_futures=True)
