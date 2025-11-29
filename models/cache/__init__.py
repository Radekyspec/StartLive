from os import remove
from pathlib import Path
from platform import system

from constant import CacheType

_cache_dir: dict[CacheType, Path] = {}


def cache_base_dir(kind: CacheType) -> Path:
    if kind in _cache_dir:
        return Path(_cache_dir[kind])
    if (_arch := system()) == "Windows":
        try:
            _base_dir = Path(__compiled__.containing_dir).resolve()
        except NameError:
            _base_dir = Path("").resolve()
        _base_dir = _base_dir / kind
    elif _arch == "Linux":
        _base_dir = Path.home() / ".cache" / "StartLive" / kind
    elif _arch == "Darwin":
        if kind == CacheType.CONFIG:
            _base_dir = Path.home() / "Library" / "Application Support" / "StartLive"
        elif kind == CacheType.LOGS:
            _base_dir = Path.home() / "Library" / "Logs" / "StartLive"
        else:
            raise ValueError("Unsupported cache type")
    else:
        raise ValueError("Unsupported system")
    _cache_dir[kind] = _base_dir
    return _base_dir


def get_cache_path(kind: CacheType, f_name: str, /, *,
                   is_makedir: bool = True) -> tuple[Path, Path]:
    _base_dir = cache_base_dir(kind)
    _const_path = _base_dir / f_name
    if is_makedir:
        _base_dir.mkdir(parents=True, exist_ok=True)
    return _base_dir, _const_path


def del_cache_user(uid: str):
    _, _title_f = get_cache_path(CacheType.CONFIG, f"title{uid}")
    if _title_f.exists():
        remove(_title_f)
