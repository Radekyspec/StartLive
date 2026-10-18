class DanmakuError(Exception):
    """Room message failure safe to display without credentials."""


class DanmakuProtocolError(DanmakuError):
    def __init__(self, message, *, response=None):
        super().__init__(message)
        self.response = response


class DanmakuAuthenticationError(DanmakuError):
    pass


class DanmakuTokenExpired(DanmakuAuthenticationError):
    """Goim code -101 requires a new token and queue context."""


class DanmakuConnectionError(DanmakuError):
    """Transport failure eligible for reconnect."""
