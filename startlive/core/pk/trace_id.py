"""Controller attempt IDs. Generate once and reuse across its HTTP requests."""
from time import time_ns
from uuid import uuid4


def new_trace_id() -> str:
    return f"PC_LINK:{str(uuid4()).lower()}:{time_ns() // 1_000_000}"
