from logging import Formatter
from re import compile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_URL_PATTERN = compile(r'https?://[^\s\'"<>]+')
_SENSITIVE_QUERY_PARAMETERS = frozenset(
    {"csrf", "csrf_token", "qrcode_key"})


def _redact_sensitive_query_parameters(text: str) -> str:
    def redact_url(match) -> str:
        url = match.group(0)
        parsed_url = urlsplit(url)
        query_pairs = parse_qsl(parsed_url.query, keep_blank_values=True)
        if not any(key.casefold() in _SENSITIVE_QUERY_PARAMETERS
                   for key, _ in query_pairs):
            return url

        redacted_pairs = [
            (key, "REDACTED" if key.casefold() in _SENSITIVE_QUERY_PARAMETERS
             else value)
            for key, value in query_pairs
        ]
        return urlunsplit(parsed_url._replace(query=urlencode(redacted_pairs)))

    return _URL_PATTERN.sub(redact_url, text)


class ThreadClassFormatter(Formatter):
    def format(self, record) -> str:
        record.threadClassName = getattr(record, 'threadClassName', 'N/A')
        return super().format(record)

    def formatException(self, exc_info) -> str:
        return _redact_sensitive_query_parameters(
            super().formatException(exc_info))
