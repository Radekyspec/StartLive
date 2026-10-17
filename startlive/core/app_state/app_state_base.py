from copy import deepcopy
from dataclasses import dataclass, field, fields, MISSING
from threading import RLock
from typing import Any, Mapping, Iterator, Tuple, ClassVar


class _StateMeta(type):
    _creation_lock = RLock()

    def __call__(cls, *args, **kwargs):
        # Protect allocation AND dataclass initialization. Returning an existing
        # object from __new__ alone would still run its generated __init__ again.
        with _StateMeta._creation_lock:
            instance = cls.__dict__.get("_instance")
            if instance is None:
                instance = super().__call__(*args, **kwargs)
                cls._instance = instance
            return instance


def _snapshot_value(value: Any) -> Any:
    # Copy value containers, but preserve opaque resources (e.g. Qt objects).
    if isinstance(value, (dict, list, set, tuple, bytearray)):
        return deepcopy(value)
    return value


@dataclass(slots=True)
class StateBase(metaclass=_StateMeta):
    _lock: Any = field(init=False, repr=False, compare=False)
    _dirty: bool = field(init=False, repr=False, compare=False)
    _initialized: bool = field(init=False, repr=False, compare=False)

    _instance: ClassVar["StateBase | None"] = None

    def __post_init__(self):
        self._lock = RLock()
        self._dirty = False
        self._initialized = True

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or not getattr(self, "_initialized", False):
            object.__setattr__(self, name, value)
            return
        if name not in self._field_names():
            raise AttributeError(name)
        self._apply_changes({name: value}, dirty=True)

    def _field_names(self) -> set[str]:
        return {f.name for f in fields(self) if not f.name.startswith("_")}

    def _apply_changes(self, values: Mapping[str, Any], *, dirty: bool) -> None:
        with self._lock:
            changes = {name: _snapshot_value(value) for name, value in
                       values.items()}
            changed = any(
                getattr(self, name) != value for name, value in changes.items())
            for name, value in changes.items():
                object.__setattr__(self, name, value)
            self._dirty = dirty
        if changed:
            # Subscribers may read or update the state; never call them under its lock.
            self._on_change()

    def _on_change(self) -> None:
        pass

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            if not hasattr(self, key):
                raise KeyError(key)
            return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._field_names():
            raise KeyError(key)
        self._apply_changes({key: value}, dirty=True)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return getattr(self, key, default)

    def update(self, mapping: Mapping[str, Any] | None = None,
               **kwargs: Any) -> None:
        values = dict(mapping) if mapping is not None else {}
        values.update(kwargs)
        names = self._field_names()
        self._apply_changes(
            {key: value for key, value in values.items() if key in names},
            dirty=True)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                f.name: _snapshot_value(getattr(self, f.name))
                for f in fields(self)
                if not f.name.startswith("_")
            }

    @classmethod
    def default_dict(cls) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(cls):
            # 跳过内部字段（比如 _lock）。
            if f.name.startswith("_"):
                continue
            if f.default_factory is not MISSING:
                value = f.default_factory()
            elif f.default is not MISSING:
                value = deepcopy(f.default)
            else:
                value = None
            result[f.name] = value
        return result

    def reset(self) -> None:
        self._apply_changes(type(self).default_dict(), dirty=False)

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
        with self._lock:
            return hasattr(self, key)

    def __len__(self) -> int:
        return len(self._field_names())

    def __bool__(self) -> bool:
        with self._lock:
            return self._dirty
