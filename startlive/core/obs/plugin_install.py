"""Install the bundled PK plugin into OBS's standard third-party locations."""

import os
import shutil
from pathlib import Path
from platform import system
from tempfile import NamedTemporaryFile

from startlive.core.exceptions import MissingPkPluginError


def _copy_binary(source: Path, destination: Path) -> str:
    """Stage each file beside its destination so a failed copy keeps the old one."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, prefix=".startlive-pk-",
                            delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        shutil.copy2(source, staging)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return str(destination)


def install_pk_plugin(resources_path: Path) -> Path:
    """Copy only the current platform's plugin; return the installed directory.

    Windows supports both OBS 33's flat layout and the earlier bin/64bit
    layout. OBS 33 prefers the flat copy and skips the duplicate legacy copy.
    See https://obsproject.com/kb/legacy-plugin-locations and
    https://obsproject.com/kb/plugins-guide. Portable OBS and Linux Flatpak
    installations require their own installation procedure.
    """
    resources_path = Path(resources_path)
    platform = system()
    if platform == "Darwin":
        source = resources_path / "obs-startlive-pk.plugin"
        if not all((source / relative).is_file() for relative in (
                "Contents/Info.plist", "Contents/MacOS/obs-startlive-pk")):
            raise MissingPkPluginError(str(source))
        destination = (
                    Path.home() / "Library/Application Support/obs-studio/plugins"
                    / source.name)
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True,
                        copy_function=_copy_binary)
        return destination

    filename = {"Windows": "obs-startlive-pk.dll",
                "Linux": "obs-startlive-pk.so"}.get(platform)
    if filename is None or not (resources_path / filename).is_file():
        raise MissingPkPluginError(str(resources_path))
    source = resources_path / filename
    if platform == "Windows":
        root = Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData")
    else:
        root = Path(
            os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        if not root.is_absolute():
            root = Path.home() / ".config"
    destination = root / "obs-studio" / "plugins" / "obs-startlive-pk"
    (destination / "data" / "locale").mkdir(parents=True, exist_ok=True)
    _copy_binary(source, destination / "bin" / "64bit" / filename)
    if platform == "Windows":
        _copy_binary(source, destination / filename)
    return destination
