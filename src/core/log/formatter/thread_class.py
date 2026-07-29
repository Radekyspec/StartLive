from logging import Formatter
from re import compile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_URL_PATTERN = compile(r'https?://[^\s\'"<>]+')
_SENSITIVE_QUERY_PARAMETERS = frozenset(
    k.casefold() for k in ("csrf", "csrf_token", "qrcode_key")
)


def _redact(text: str) -> str:
    if not text:
        return text

    def redact_url(match):
        url = match.group(0)
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if not any(
                k.casefold() in _SENSITIVE_QUERY_PARAMETERS for k, _ in pairs):
            return url
        redacted = [
            (k,
             "REDACTED" if k.casefold() in _SENSITIVE_QUERY_PARAMETERS else v)
            for k, v in pairs
        ]
        return urlunsplit(parsed._replace(query=urlencode(redacted)))

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
