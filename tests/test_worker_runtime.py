import unittest
from threading import Condition
from unittest.mock import Mock, patch

from src.core import app_state
from src.core.constant import LoginResult
from src.core.workers.base import BaseWorker, CancellationToken
from src.core.workers.login.fetch_login import FetchLoginWorker
from src.core.workers.obs_ws.obs_connector import ObsConnectorWorker


class _Response:
    def __init__(self, code: int) -> None:
        self.encoding = ""
        self._code = code
        self.cookies = Mock()

    def json(self) -> dict[str, object]:
        return {"data": {"code": self._code}, "message": "test"}


class WorkerRuntimeTests(unittest.TestCase):
    def test_require_session_fails_clearly_when_disabled(self) -> None:
        worker = BaseWorker("sessionless", with_session=False)

        with self.assertRaisesRegex(
            RuntimeError,
            "sessionless requires an HTTP session",
        ):
            worker.require_session()

    def test_login_poll_accepts_missing_progress_callback(self) -> None:
        session = Mock()
        session.get.side_effect = [_Response(86090), _Response(86038)]
        previous = app_state.scan_status.as_dict()
        app_state.scan_status.update({
            "qr_key": "key",
            "scanned": False,
            "timeout": False,
            "wait_for_confirm": False,
        })
        try:
            with (
                patch(
                    "src.core.workers.base.BaseWorker.create_session",
                    return_value=session,
                ),
                patch("src.core.workers.login.fetch_login.sleep"),
            ):
                worker = FetchLoginWorker(Mock())
                result = worker.run(None)
        finally:
            app_state.scan_status.update(previous)

        self.assertEqual(result, LoginResult.QR_EXPIRED)
        self.assertEqual(session.get.call_count, 2)

    def test_obs_connector_accepts_missing_progress_callback(self) -> None:
        condition = Condition()
        worker = ObsConnectorWorker(
            Mock(),
            "localhost",
            4455,
            "password",
            cond=condition,
        )

        with patch(
            "src.core.workers.obs_ws.obs_connector.ReqClient",
            return_value=Mock(),
        ) as req_client:
            worker.run(None)

        req_client.assert_called_once_with(
            host="localhost",
            port=4455,
            password="password",
            timeout=5,
        )

    def test_cancellation_continues_after_callback_raises(self) -> None:
        token = CancellationToken()
        calls: list[str] = []

        def fail() -> None:
            calls.append("first")
            raise RuntimeError("callback failed")

        token.add_cancel_callback(fail)
        token.add_cancel_callback(lambda: calls.append("second"))

        token.cancel()

        self.assertEqual(calls, ["first", "second"])
        self.assertTrue(token)


if __name__ == "__main__":
    unittest.main()
