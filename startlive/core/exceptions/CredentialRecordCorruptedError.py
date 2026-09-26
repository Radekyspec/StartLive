class CredentialRecordCorruptedError(Exception):
    key: str
    reason: str
    """Raised when a persisted credential record cannot be safely used."""

    def __init__(self, key: str, reason: str):
        self.key = key
        self.reason = reason
        super().__init__(f"{key}: {reason}")

    def __repr__(self):
        return f"{self.key}: {self.reason}"
