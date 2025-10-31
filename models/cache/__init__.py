from os import makedirs, remove
from os.path import join, expanduser, abspath, exists
from platform import system

from constant import CacheType

_cache_dir: dict[CacheType, str] = {}


def cache_base_dir(kind: CacheType) -> str:
    if kind in _cache_dir:
        return _cache_dir[kind]
    if (_arch := system()) == "Windows":
        try:
            _base_dir = abspath(__compiled__.containing_dir)
        except NameError:
            _base_dir = abspath("")
        _base_dir = join(_base_dir, kind)
    elif _arch == "Linux":
        _base_dir = join(expanduser("~"), ".cache", "StartLive",
                         kind)
    elif _arch == "Darwin":
        if kind == CacheType.CONFIG:
            _base_dir = join(expanduser("~"), "Library",
                             "Application Support", "StartLive")
        elif kind == CacheType.LOGS:
            _base_dir = join(expanduser("~"), "Library",
                             "Logs", "StartLive")
        else:
            raise ValueError("Unsupported cache type")
    else:
        raise ValueError("Unsupported system")
    _cache_dir[kind] = _base_dir
    return _base_dir


def get_cache_path(kind: CacheType, f_name: str, /, *,
                   is_makedir: bool = True) -> tuple[str, str]:
    _base_dir = cache_base_dir(kind)
    _const_path = join(_base_dir, f_name)
    if is_makedir:
        makedirs(_base_dir, exist_ok=True)
    return _base_dir, _const_path


def del_cache_user(uid: str):
    _, _title_f = get_cache_path(CacheType.CONFIG, f"title{uid}")
    if exists(_title_f):
        remove(_title_f)
