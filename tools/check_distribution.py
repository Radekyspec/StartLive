"""Check a built wheel and smoke-test its installed command outside the checkout."""

import argparse
import configparser
import email
import os
import subprocess
import tempfile
import venv
import zipfile
from pathlib import Path


def run(*args, cwd, env):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--tag",
                        help="Release tag, which must match the wheel version")
    args = parser.parse_args()
    wheel = args.wheel.resolve()

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_name = next(
            n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_name))
        if metadata["Name"] != "startlive":
            raise ValueError("Unexpected distribution name")
        version = metadata["Version"]
        if args.tag and args.tag.removeprefix("v") != version:
            raise ValueError(
                f"Release tag {args.tag!r} does not match {version!r}")
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(archive.read(
            metadata_name.replace("METADATA", "entry_points.txt")
        ).decode())
        if entrypoints["console_scripts"]["startlive"] != "StartLive:cli":
            raise ValueError("Missing startlive command")
        required = {
            "StartLive.py", "startlive/core/runtime.py",
            "startlive/core/constant/_version.py",
            "startlive/PySide/window/main_window.py",
            "startlive/resources/icon_left.ico",
            "startlive/resources/icon_left_macOS.ico",
            "startlive/resources/version.json",
        }
        required.update(
            f"startlive/resources/{theme}-{icon}.svg"
            for theme in ("dark", "light")
            for icon in ("home", "log", "menu", "settings", "theme")
        )
        missing = required - names
        if missing:
            raise ValueError(f"Missing application files: {sorted(missing)}")
        for name in names:
            if (name.endswith((".pyc", ".pyo", ".qss"))
                    or "__pycache__" in name.split("/")
                    or name.split("/")[0] in {"config", "logs", "tests",
                                              "build", ".idea"}):
                raise ValueError(f"Unexpected development/user file: {name}")

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="startlive-wheel-") as directory:
        directory = Path(directory)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        command = scripts / (
            "startlive.exe" if os.name == "nt" else "startlive")
        # Help/version must work without initializing Qt, keyring or network services.
        run(str(python), "-m", "pip", "install", "--no-deps", "--no-index",
            str(wheel), cwd=directory, env=env)
        run(str(command), "--help", cwd=directory, env=env)
        # Windows CI may redirect stdout using a legacy code page. Exercise
        # this explicitly even when the machine running this check uses UTF-8.
        for encoding in ("cp1252", "ascii", "utf-8"):
            help_env = dict(env, PYTHONIOENCODING=f"{encoding}:strict")
            help_result = subprocess.run(
                [str(command), "--help"], cwd=directory, env=help_env,
                check=True, capture_output=True, text=True, encoding=encoding,
            )
            if "--web.port" not in help_result.stdout:
                raise ValueError(f"Incomplete help output with {encoding}")
        result = subprocess.run(
            [str(command), "--version"], cwd=directory, env=env,
            check=True, capture_output=True, text=True,
        )
        if result.stdout.strip() != f"StartLive {version}":
            raise ValueError(f"Incorrect installed version: {result.stdout!r}")
        run(str(python), "-I", "-c", """
from pathlib import Path
import StartLive
from startlive.core import cache, runtime
from startlive.core.constant import CacheType
runtime.package_managed = True
root = Path(StartLive.__file__).parent
assert (root / "startlive" / "resources" / "icon_left.ico").is_file()
assert (root / "startlive" / "resources" / "dark-home.svg").is_file()
assert not cache.cache_base_dir(CacheType.CONFIG).is_relative_to(root)
""", cwd=directory, env=env)
    print(
        f"Verified {wheel.name}: contents, isolated installation, command and resources")


if __name__ == "__main__":
    main()
