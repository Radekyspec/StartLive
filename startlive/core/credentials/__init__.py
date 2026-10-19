"""Credential operations; data-only states do not initialize the application."""
from startlive.core.exceptions import (
    CredentialIndexCorruptedError,
    CredentialRecordCorruptedError,
    CredentialTransactionError,
)
from .states import RemovedCredential, StoredCredential

__all__ = [
    "CredentialIndexCorruptedError", "CredentialRecordCorruptedError",
    "CredentialStore", "CredentialTransactionError", "RemovedCredential",
    "StoredCredential",
]


def __getattr__(name):
    if name == "CredentialStore":
        from .store import CredentialStore
        globals()[name] = CredentialStore
        return CredentialStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
