class CredentialRecordCorruptedError(Exception):
    """Raised when a persisted credential record cannot be safely used."""

    def __init__(self, key: str, reason: str):
        super().__init__(f"{key}: {reason}")
