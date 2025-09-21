from typing import Iterator, Iterable, Any, Tuple

from PySide6.QtCore import QMutex, QMutexLocker


class ThreadSafeDict:
    def __init__(self, value: dict | None = None):
        self._dict: dict = {} if value is None else value
        self._lock = QMutex()

    @staticmethod
    def new(value: dict | None = None) -> "ThreadSafeDict":
        if value is None:
            return ThreadSafeDict()
        return ThreadSafeDict(value.copy())

    def __bool__(self) -> bool:
        with QMutexLocker(self._lock):
            return bool(self._dict)

    def __len__(self) -> int:
        with QMutexLocker(self._lock):
            return len(self._dict)

    def __contains__(self, key: Any) -> bool:
        with QMutexLocker(self._lock):
            return key in self._dict

    def __iter__(self) -> Iterator[Any]:
        with QMutexLocker(self._lock):
            keys_snapshot = list(self._dict.keys())
        return iter(keys_snapshot)

    def values(self) -> Iterator[Any]:
        with QMutexLocker(self._lock):
            vals_snapshot = list(self._dict.values())
        return iter(vals_snapshot)

    def items(self) -> Iterator[Tuple[Any, Any]]:
        with QMutexLocker(self._lock):
            items_snapshot = list(self._dict.items())
        return iter(items_snapshot)

    def __getitem__(self, key: Any) -> Any:
        return self._dict[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        with QMutexLocker(self._lock):
            self._dict[key] = value

    def __delitem__(self, key: Any) -> None:
        with QMutexLocker(self._lock):
            del self._dict[key]

    def get(self, key: Any, default: Any = None) -> Any:
        return self._dict.get(key, default)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        with QMutexLocker(self._lock):
            return self._dict.setdefault(key, default)

    def pop(self, key: Any, default: Any = ...):
        with QMutexLocker(self._lock):
            if default is ...:
                return self._dict.pop(key)
            return self._dict.pop(key, default)

    def popitem(self):
        with QMutexLocker(self._lock):
            return self._dict.popitem()

    def clear(self) -> None:
        with QMutexLocker(self._lock):
            self._dict.clear()

    def update(self, value: Iterable[Tuple[Any, Any]] | dict = (),
               **kwargs) -> None:
        with QMutexLocker(self._lock):
            self._dict.update(value, **kwargs)

    def copy(self) -> dict:
        with QMutexLocker(self._lock):
            return dict(self._dict)

    def __repr__(self) -> str:
        with QMutexLocker(self._lock):
            return f"{self.__class__.__name__}({repr(self._dict)})"

    @property
    def internal(self) -> dict:
        return self._dict
