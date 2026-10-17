from startlive.core.constant.logging import _URL_PATTERN, \
    _SENSITIVE_QUERY_PARAMETERS
from logging import Formatter
from urllib.parse import parse_qsl, urlencode, urlsplit


def _redact(text: str) -> str:
    if not text:
        return text

    def redact_url(match):
        prefix = match.group("prefix") or ""
        url = match.group("absolute") or match.group("relative")

        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)

        if not any(
                key.casefold() in _SENSITIVE_QUERY_PARAMETERS
                for key, _ in pairs
        ):
            return match.group(0)

        redacted_pairs = [
            (
                key,
                "REDACTED"
                if key.casefold() in _SENSITIVE_QUERY_PARAMETERS
                else value,
            )
            for key, value in pairs
        ]

        return prefix + parsed._replace(
            query=urlencode(redacted_pairs)).geturl()

    return _URL_PATTERN.sub(redact_url, text)


class ThreadClassFormatter(Formatter):
    def format(self, record) -> str:
        record.threadClassName = getattr(record, 'threadClassName', 'N/A')
        record.exc_text = None
        try:
            return super().format(record)
        finally:
            record.exc_text = None

    def formatException(self, exc_info) -> str:
        return _redact(
            super().formatException(exc_info))
