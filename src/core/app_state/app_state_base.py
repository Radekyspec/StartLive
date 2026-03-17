from copy import deepcopy
from dataclasses import dataclass, field, fields, MISSING
from typing import Any, Mapping, Iterator, Tuple

from PySide6.QtCore import QMutex, QMutexLocker


@dataclass(slots=True)
class StateBase:
    _lock: QMutex = field(default_factory=QMutex, init=False, repr=False)
    _dirty: bool = False

    # obj["field"]
    def __getitem__(self, key: str) -> Any:
        with QMutexLocker(self._lock):
            if not hasattr(self, key):
                raise KeyError(key)
            return getattr(self, key)

    # obj["field"] = value
    def __setitem__(self, key: str, value: Any) -> None:
        self._dirty = True
        with QMutexLocker(self._lock):
            if not hasattr(self, key):
                raise KeyError(key)
            setattr(self, key, value)

    # obj.get("field", default)
    def get(self, key: str, default: Any = None) -> Any:
        with QMutexLocker(self._lock):
            if not hasattr(self, key):
                return default
            return getattr(self, key)

    # obj.update({...})
    def update(self, mapping: Mapping[str, Any] | None = None,
               **kwargs: Any) -> None:
        self._dirty = True
        with QMutexLocker(self._lock):
            if mapping:
                for k, v in mapping.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)

    def as_dict(self) -> dict[str, Any]:
        with QMutexLocker(self._lock):
            return {
                f.name: getattr(self, f.name)
                for f in fields(self)
                if not f.name.startswith("_")
            }

    @classmethod
    def default_dict(cls) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(cls):
            # 跳过内部字段（比如 _lock）
            if f.name.startswith("_"):
                continue

            if f.default_factory is not MISSING:
                value = f.default_factory()
            elif f.default is not MISSING:
                # 防止用到可变对象，做一层 deepcopy 稳妥
                value = deepcopy(f.default)
            else:
                value = None

            result[f.name] = value
        return result

    def reset(self) -> None:
        self._dirty = False
        defaults = type(self).default_dict()
        with QMutexLocker(self._lock):
            for name, value in defaults.items():
                setattr(self, name, value)

    @property
    def internal(self) -> dict[str, Any]:
        return self.as_dict()

    def items(self) -> Iterator[Tuple[str, Any]]:
        return iter(self.as_dict().items())

    def values(self) -> Iterator[Any]:
        return iter(self.as_dict().values())

    def keys(self) -> Iterator[str]:
        return iter(self.as_dict().keys())

    def __iter__(self) -> Iterator[str]:
        return self.keys()

    def __contains__(self, key: str) -> bool:
        with QMutexLocker(self._lock):
            return hasattr(self, key)

    def __len__(self) -> int:
        with QMutexLocker(self._lock):
            return len([f for f in fields(self) if not f.name.startswith("_")])

    def __bool__(self) -> bool:
        return self._dirty
