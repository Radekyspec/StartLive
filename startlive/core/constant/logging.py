from re import compile, IGNORECASE, VERBOSE

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
