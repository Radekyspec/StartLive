"""Reject Nuitka releases missing the installable OBS plugin or PK dependencies."""

import argparse
import hashlib
import platform
import plistlib
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def check_distribution(source: Path, resources: Path, report: Path,
                       system: str):
    xml = ET.parse(report).getroot()
    modules = {node.attrib["name"] for node in xml.findall("module")}
    required_modules = {"aiortc", "aioice", "av", "pylibsrtp",
                        "startlive.core.pk.rtc_connection",
                        "startlive.core.pk.rtc_media"}
    if missing := required_modules - modules:
        raise ValueError(
            f"Missing PK modules in Nuitka report: {sorted(missing)}")
    metadata = {node.attrib["name"] for node in
                xml.findall("metadata/included_metadata")}
    if missing := {"aiortc", "aioice"} - metadata:
        raise ValueError(f"Missing PK version metadata: {sorted(missing)}")
    included = {
        node.attrib["name"].replace("\\", "/")
        for node in xml.findall("data_file")
        if "inhibit" not in node.get("tags", "").split(",")
    }

    if system == "Windows":
        files = [Path("obs-startlive-pk.dll")]
    elif system == "Darwin":
        bundle = Path("obs-startlive-pk.plugin")
        files = [path.relative_to(source) for path in
                 (source / bundle).rglob("*")
                 if path.is_file() and "_CodeSignature" not in path.parts]
        for required in (bundle / "Contents/Info.plist",
                         bundle / "Contents/MacOS/obs-startlive-pk"):
            if required not in files:
                raise ValueError(
                    f"Missing source plugin file: {source / required}")
    else:
        raise ValueError(f"Unsupported build platform: {system}")

    for relative in files:
        original, packaged = source / relative, resources / relative
        for path in (original, packaged):
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Missing or empty plugin file: {path}")
        if f"resources/{relative.as_posix()}" not in included:
            raise ValueError(
                f"Plugin file missing from Nuitka report: {relative}")
        # Nuitka signs Mach-O files; code-signature bytes can legitimately change.
        if system == "Darwin" and relative.name == "obs-startlive-pk":
            continue
        if hashlib.sha256(original.read_bytes()).digest() != hashlib.sha256(
                packaged.read_bytes()).digest():
            raise ValueError(
                f"Plugin file changed during packaging: {relative}")

    if system == "Darwin":
        with (resources / "obs-startlive-pk.plugin/Contents/Info.plist").open(
                "rb") as stream:
            info = plistlib.load(stream)
        if (info.get("CFBundleExecutable") != "obs-startlive-pk"
                or info.get("CFBundlePackageType") != "BNDL"):
            raise ValueError("Invalid OBS plugin bundle metadata")


def check_macos_binary(binary: Path):
    """Use Apple's tools to check the real binary on the native CI runner."""
    subprocess.run(["lipo", str(binary), "-verify_arch", platform.machine()],
                   check=True)
    linked = subprocess.check_output(["otool", "-L", str(binary)], text=True)
    for line in linked.splitlines()[1:]:
        dependency = line.strip().split(" (", 1)[0]
        if not dependency.startswith(
                ("@rpath/", "@loader_path/", "@executable_path/",
                 "/usr/lib/", "/System/Library/")):
            raise ValueError(
                f"Plugin links to a build-machine library: {dependency}")
    load_commands = subprocess.check_output(["otool", "-l", str(binary)],
                                            text=True)
    if "path @executable_path/../Frameworks (offset" not in load_commands:
        raise ValueError(
            "Plugin is missing the OBS Frameworks runtime search path")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path("startlive/resources"))
    parser.add_argument("--report", type=Path,
                        default=Path("build/nuitka-report.xml"))
    args = parser.parse_args()
    system = platform.system()
    if system == "Darwin":
        app = Path("build/StartLive.app")
        resources = app / "Contents/MacOS/resources"
    else:
        resources = Path("build/StartLive.dist/resources")
    check_distribution(args.source, resources, args.report, system)
    if system == "Darwin":
        plugin = resources / "obs-startlive-pk.plugin"
        check_macos_binary(plugin / "Contents/MacOS/obs-startlive-pk")
        for bundle in (plugin, app):
            subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(bundle)],
                check=True)
    print(f"Verified {system} OBS PK plugin, PK modules and version metadata")


if __name__ == "__main__":
    main()
