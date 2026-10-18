class PkError(Exception):
    """A PK operation failed without exposing account credentials."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PkProtocolError(PkError):
    """The server response or protocol configuration is invalid."""


class PkAuthenticationError(PkError):
    """The PK session no longer belongs to the active account."""
