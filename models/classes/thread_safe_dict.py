from threading import Lock


class ThreadSafeDict:
    def __init__(self, value: dict):
        self._dict: dict = value
        self._lock = Lock()

    def __bool__(self):
        return bool(self._dict)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._dict[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._dict[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._dict

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def __repr__(self):
        with self._lock:
            return repr(self._dict)

    def update(self, value, **kwargs):
        with self._lock:
            self._dict.update(value, **kwargs)

    @property
    def internal(self) -> dict:
        return self._dict
