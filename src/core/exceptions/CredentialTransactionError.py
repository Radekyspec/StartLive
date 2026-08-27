class CredentialTransactionError(Exception):
    """Raised when a credential write cannot be durably completed."""

    def __init__(
            self,
            operation: str,
            primary_error: Exception,
            rollback_error: Exception | None = None,
    ):
        super().__init__(f"{operation} credential transaction failed")
        self.operation = operation
        self.primary_error = primary_error
        self.rollback_error = rollback_error
        # Short aliases keep callers from having to inspect exception details.
        self.primary = primary_error
        self.rollback = rollback_error
