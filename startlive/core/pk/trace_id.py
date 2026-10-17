"""Controller attempt IDs. Generate once and reuse across its HTTP requests."""
from time import time_ns
from uuid import uuid4


def new_trace_id(*, clock_ns=time_ns, uuid_factory=uuid4) -> str:
    return f"PC_LINK:{str(uuid_factory()).lower()}:{clock_ns() // 1_000_000}"
