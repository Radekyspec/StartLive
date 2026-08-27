import sys
import unittest
from unittest.mock import Mock, patch

import StartLive
from src.PySide.updater.update_worker import VelopackUpdateWorker


class LinuxStartupTests(unittest.TestCase):
    def tearDown(self) -> None:
        StartLive._velopack_first_run = False

    @patch("StartLive.system", return_value="Linux")
    def test_velopack_hooks_are_skipped_on_linux(self, _system: Mock) -> None:
        with patch.dict(sys.modules, {"velopack": None}):
            StartLive._run_velopack_hooks()

    @patch("StartLive.system", return_value="Darwin")
    def test_velopack_hooks_run_on_non_linux(self, _system: Mock) -> None:
        app = Mock()
        app.on_first_run.return_value = app
        app_factory = Mock(return_value=app)
        velopack = Mock(App=app_factory)

        with patch.dict(sys.modules, {"velopack": velopack}):
            StartLive._run_velopack_hooks()

        app_factory.assert_called_once_with()
        app.on_first_run.assert_called_once_with(
            StartLive._on_velopack_first_run
        )
        app.run.assert_called_once_with()

        first_run_callback = app.on_first_run.call_args.args[0]
        first_run_callback("1.0.0")
        self.assertTrue(StartLive._velopack_first_run)

    @patch(
        "src.PySide.updater.update_worker.system",
        return_value="Linux",
    )
    def test_update_worker_finishes_without_velopack(self, _system: Mock) -> None:
        progress = Mock()
        worker = VelopackUpdateWorker("https://example.invalid", progress)
        finished = Mock()
        failed = Mock()
        worker.finished.connect(finished)
        worker.failed.connect(failed)

        with patch.dict(sys.modules, {"velopack": None}):
            worker.run()

        finished.assert_called_once_with()
        failed.assert_not_called()
        progress.assert_not_called()


if __name__ == "__main__":
    unittest.main()
