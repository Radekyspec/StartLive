"""Application-scoped credentials, with volatile storage on minimal Linux desktops."""
import logging
from platform import system
from threading import RLock

import keyring
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as UnavailableKeyring
from keyring.backends.null import Keyring as DisabledKeyring
from keyring.errors import PasswordDeleteError


class _SessionKeyring:
    def __init__(self):
        self._values: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    def get_password(self, service: str, username: str) -> str | None:
        with self._lock:
            return self._values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        with self._lock:
            self._values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        with self._lock:
            try:
                del self._values[service, username]
            except KeyError:
                raise PasswordDeleteError("No such password") from None


_backend: KeyringBackend | _SessionKeyring | None = None
_selection_lock = RLock()


def _get_backend() -> KeyringBackend | _SessionKeyring:
    global _backend
    with _selection_lock:
        if _backend is None:
            selected = keyring.get_keyring()
            if system() == "Linux" and isinstance(
                    selected, (UnavailableKeyring, DisabledKeyring)):
                _backend = _SessionKeyring()
                logging.getLogger(__name__).warning(
                    "No system keyring is available; login credentials and OBS "
                    "passwords will only be kept for this StartLive session."
                )
            else:
                _backend = selected
        return _backend


def using_session_keyring() -> bool:
    """Report the selected mode without initializing a backend on the UI thread."""
    return isinstance(_backend, _SessionKeyring)


def get_password(service: str, username: str) -> str | None:
    return _get_backend().get_password(service, username)


def set_password(service: str, username: str, password: str) -> None:
    _get_backend().set_password(service, username, password)


def delete_password(service: str, username: str) -> None:
    _get_backend().delete_password(service, username)
