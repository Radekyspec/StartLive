"""Credential operations; data-only states do not initialize the application."""
from .states.results import RemovedCredential, StoredCredential
from startlive.core.exceptions import (
    CredentialIndexCorruptedError,
    CredentialRecordCorruptedError,
    CredentialTransactionError,
)

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
