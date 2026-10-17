"""Shared synchronous JSON exchange; workers own sessions and scheduling.

Domain APIs own signing, business-code validation and diagnostic redaction.
Bodies are already encoded: do not normalize them or retry mutating GETs.
"""
from abc import ABC, abstractmethod
from time import monotonic
from typing import Any, Protocol

from requests import RequestException, Response, Session


class HttpIdentity(Protocol):
    """The shared transport only needs the captured device identifier."""

    @property
    def buvid(self) -> str: ...


class JsonHttpApi(ABC):
    """Domain adapters supply response validation and safe diagnostic policies.

    Their constructors bind the worker-owned session and account snapshot.
    The transport neither creates nor closes that session.
    """
    session: Session
    identity: HttpIdentity
    _http_label: str
    _http_error: type[Exception]
    _http_protocol_error: type[Exception]

    @abstractmethod
    def _http_context(self, operation: str, method: str, path: str,
                      fields: dict[str, Any]) -> dict[str, Any]:
        """Return domain-specific request context safe for diagnostics."""
        raise NotImplementedError

    @abstractmethod
    def _response_fields(self, response: Response, parsed: Any) -> dict[
        str, Any]:
        """Extract response diagnostics using the domain's redaction policy."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _http_trace(event: str, **fields: Any) -> None:
        """Write diagnostics through the domain's logger."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _parse_response(operation: str, result: Any) -> Any:
        """Validate business codes and produce the domain result."""
        raise NotImplementedError

    @abstractmethod
    def _parsed_log_value(self, parsed: Any) -> Any:
        """Convert a parsed result to a safe diagnostic value."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _http_failure_fields(error: Exception, response: Response | None,
                             stage: str, elapsed: float, *, network: bool) -> \
    dict[str, Any]:
        """Describe failures without exposing signed URLs or credentials."""
        raise NotImplementedError

    def _send(self, operation, method, path, body, *, request_fields=None,
              parse_result=None):
        context = self._http_context(operation, method, path,
                                     request_fields or {})
        started = monotonic()
        response = result = None
        response_fields = {"http_status": None, "response": None}
        stage = "send"
        headers = {"buvid": self.identity.buvid} if self.identity.buvid else {}
        url = "https://api.live.bilibili.com" + path

        def elapsed():
            return round((monotonic() - started) * 1000, 3)

        def record_response():
            nonlocal response_fields
            response_fields = self._response_fields(response, result)
            self._http_trace("http.response", **context, **response_fields,
                             elapsed_ms=elapsed())

        try:
            try:
                if method == "GET":
                    response = self.session.get(url, params=body,
                                                headers=headers,
                                                allow_redirects=False)
                else:
                    response = self.session.post(url, data=body.encode("utf-8"),
                                                 headers=headers | {
                                                     "Content-Type": "application/x-www-form-urlencoded"},
                                                 allow_redirects=False)
                stage = "response"
                if response.status_code != 200:
                    raise self._http_error(
                        f"{self._http_label}请求失败（HTTP {response.status_code}）")
                try:
                    result = response.json()
                except ValueError:
                    # requests.JSONDecodeError also inherits RequestException.
                    raise self._http_protocol_error(
                        f"{self._http_label}服务返回了无效 JSON") from None
            finally:
                if response is not None:
                    record_response()
            stage = "parse"
            parsed = self._parse_response(operation, result)
            if parse_result is not None:
                parsed = parse_result(parsed)
            try:
                self._http_trace("http.parsed", **context,
                                 result=self._parsed_log_value(parsed))
            except Exception:
                pass  # Diagnostic conversion must not turn success into failure.
            return parsed
        except RequestException as error:
            if response is None and error.response is not None:
                response = error.response
                record_response()
            self._http_trace("http.error", **context, **response_fields,
                             error_type=type(error).__name__,
                             **self._http_failure_fields(error, response, stage,
                                                         elapsed(),
                                                         network=True))
            # Exception text can contain the signed URL and account credentials.
            raise self._http_error(
                f"{self._http_label}网络请求失败，请检查连接后重试") from None
        except Exception as error:
            self._http_trace("http.error", **context, **response_fields,
                             error_type=type(error).__name__,
                             **self._http_failure_fields(error, response, stage,
                                                         elapsed(),
                                                         network=False))
            raise
        finally:
            if response is not None:
                response.close()
