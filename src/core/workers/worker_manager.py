from concurrent.futures import ThreadPoolExecutor, Future, CancelledError
from threading import RLock
from typing import Any

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
                 max_workers: int | None = None) -> None:
        self._dispatcher = dispatcher
        self._max_workers = max_workers
        self._executor = self._create_executor()
        self._jobs: dict[Future, BaseWorker] = {}
        self._worker_typeset: set[str] = set()
        self._lock = RLock()
        self.logger = get_logger(self.__class__.__name__)

    def _create_executor(self) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="backend-worker",
        )

    def submit(self, worker: BaseWorker, /,
               on_progress: bool = False) -> Future:
        if (worker_type := worker.__class__.__name__) in self._worker_typeset:
            self.logger.warning(
                f"Attempting to add {worker_type} but one already exists.")
            raise RuntimeError(
                f"Attempting to add {worker_type} but one already exists.")

        future = self._executor.submit(self._run_worker, worker,
                                       on_progress=on_progress)
        self.logger.info(f"{worker_type} added to thread pool")

        with self._lock:
            self._worker_typeset.add(worker_type)
            self._jobs[future] = worker
            future.add_done_callback(self._handle_done)
        return future

    def _run_worker(self, worker: BaseWorker | LongLiveWorker, /,
                    on_progress: bool) -> Any:
        if isinstance(worker, LongLiveWorker):
            worker.raise_if_cancelled()

        def report_progress(*args, **kwargs) -> None:
            if not on_progress:
                return
            self._dispatcher.post(worker.on_progress, *args, **kwargs)

        return worker.start(report_progress=report_progress)

    def cancel(self, job_future: Future) -> bool:
        with self._lock:
            worker = self._jobs.get(job_future, None)
        if worker is None or not isinstance(worker, LongLiveWorker):
            return False

        worker.stop()
        return job_future.cancel()

    def _handle_done(self, future: Future) -> None:
        with self._lock:
            worker = self._jobs.pop(future, None)
            if worker is None:
                return
            worker_name = worker.__class__.__name__
            self._worker_typeset.discard(worker_name)

        def finalize() -> None:
            # future canceled before start
            if future.cancelled():
                return

            try:
                result = future.result()
                self.logger.info(
                    f"{worker_name} finished with result: {result!r}")
            except (TaskCancelled, CancelledError):
                pass
            except Exception as e:
                self.logger.exception(f"{worker_name} failed")
                try:
                    worker.on_exception(e)
                except Exception:
                    self.logger.exception(f"{worker_name} on_exception failed:")
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

    def shutdown(self, cancel_running: bool = True, wait: bool = True) -> None:
        if cancel_running:
            for job_future in list(self._jobs.keys()):
                self.cancel(job_future)

        self._executor.shutdown(wait=wait, cancel_futures=True)

    def restart(self, cancel_running: bool = True) -> None:
        self.shutdown(cancel_running)
        self._jobs.clear()
        self._worker_typeset.clear()

        self._executor = self._create_executor()
        self.logger.info("Worker manager restarted")
