from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from os import cpu_count
from traceback import print_exc
from typing import Any, Callable
from uuid import uuid4

from .base import BaseWorker, LongLiveWorker
from .dispatcher import Dispatcher
from ..exceptions import TaskCancelled
from ..log import get_logger


@dataclass
class JobRecord:
    job_id: str
    name: str
    worker: BaseWorker
    future: Future


class WorkerManager:
    _dispatcher: Dispatcher
    _executor: ThreadPoolExecutor
    _jobs: dict[str, JobRecord]
    _worker_typeset: set[str]
    _future_to_job_id: dict[Future, str]

    def __init__(self, dispatcher: Dispatcher,
                 max_workers: int = cpu_count()) -> None:
        self._dispatcher = dispatcher
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="backend-worker",
        )
        self._jobs: dict[str, JobRecord] = {}
        self._worker_typeset: set[str] = set()
        self._future_to_job_id: dict[Future, str] = {}
        self.logger = get_logger(self.__class__.__name__)

    def submit(self, worker: BaseWorker, *,
               on_progress: Callable | None = None) -> str:
        if (worker_name := worker.__class__.__name__) in self._worker_typeset:
            self.logger.warning(f"Attempting to add {worker_name}"
                                f" but one already exists.")
            return ""
        worker.manager = self
        job_id = uuid4().hex

        future = self._executor.submit(self._run_worker, worker, on_progress)
        self.logger.info(f"{worker_name} added to thread pool")
        record = JobRecord(job_id=job_id, worker=worker, future=future,
                           name=worker_name)
        self._worker_typeset.add(worker_name)

        self._jobs[job_id] = record
        self._future_to_job_id[future] = job_id
        future.add_done_callback(self._handle_done)
        return job_id

    def _run_worker(self, worker: BaseWorker | LongLiveWorker,
                    on_progress: Callable | None) -> Any:
        if isinstance(worker, LongLiveWorker):
            worker.raise_if_cancelled()

        def report_progress() -> None:
            if on_progress is None:
                return
            self._dispatcher.post(on_progress)

        return worker.run(report_progress=report_progress)

    def cancel(self, job_id: str) -> bool:
        record = self._jobs.get(job_id)
        if record is None or not isinstance(record.worker, LongLiveWorker):
            return False

        record.worker.stop()
        record.future.cancel()
        return True

    def _handle_done(self, future: Future) -> None:
        job_id = self._future_to_job_id.pop(future, None)
        if job_id is None:
            return

        record = self._jobs.pop(job_id, None)
        if record is None:
            return

        worker = record.worker
        worker_name = record.name
        self._worker_typeset.remove(worker_name)

        def finalize() -> None:
            # future canceled before start
            if future.cancelled():
                return

            try:
                result = future.result()
            except TaskCancelled:
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
            for job_id in list(self._jobs.keys()):
                self.cancel(job_id)

        self._executor.shutdown(wait=False, cancel_futures=True)
