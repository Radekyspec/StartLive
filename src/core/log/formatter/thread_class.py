from logging import Formatter
from re import compile, IGNORECASE, VERBOSE
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_URL_PATTERN = compile(
    r"""
    # 普通的完整 URL
    (?P<absolute>
        https?://[^\s'"<>]+
    )

    |

    # urllib3 / requests 报错里的相对 URL
    (?P<prefix>
        \bwith\s+url:\s*
    )
    (?P<relative>
        /[^\s'"<>]+
    )
    """,
    IGNORECASE | VERBOSE,
)
_SENSITIVE_QUERY_PARAMETERS = frozenset(
    k.casefold() for k in ("csrf", "csrf_token", "qrcode_key")
)


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

        redacted_url = urlunsplit(
            parsed._replace(query=urlencode(redacted_pairs))
        )

        return prefix + redacted_url

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
