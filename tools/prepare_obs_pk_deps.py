"""Fetch the OBS 28.0.0 dependency archives used by its official build workflow."""

import argparse
import hashlib
import subprocess
import urllib.request
import zipfile
from pathlib import Path

# OBS 28.0.0's .github/workflows/main.yml pins obs-deps 2022-08-02 / Qt 6.3.1.
# macOS hashes are from that workflow; Windows hashes are of the release assets.
ARCHIVES = {
    ("Windows", "X64"): {
        "windows-deps-2022-08-02-x64.zip":
            "2192d8ce780c4281b807cd457994963669e5202659ecd92f19b54c3e7d0c1915",
        "windows-deps-qt6-2022-08-02-x64.zip":
            "e5509b54196a3f935250cc4b9c54160c8e588fd0f92bc078a2a64f9d9e2e4e93",
    },
    ("macOS", "X64"): {
        "macos-deps-2022-08-02-x86_64.tar.xz":
            "7637e52305e6fc53014b5aabd583f1a4490b1d97450420e977cae9a336a29525",
        "macos-deps-qt6-2022-08-02-universal.tar.xz":
            "252e6684f43ab9c6f262c73af739e2296ce391b998da2c4ee04c254aaa07db18",
    },
    ("macOS", "ARM64"): {
        "macos-deps-2022-08-02-arm64.tar.xz":
            "755e0fa69b17a3ae444e1befa9d91d77e3cafe628fbd1c6333686091826595cd",
        "macos-deps-qt6-2022-08-02-universal.tar.xz":
            "252e6684f43ab9c6f262c73af739e2296ce391b998da2c4ee04c254aaa07db18",
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os", choices=("Windows", "macOS"), required=True)
    parser.add_argument("--arch", choices=("X64", "ARM64"), required=True)
    args = parser.parse_args()
    archives = ARCHIVES.get((args.os, args.arch))
    if archives is None:
        parser.error(f"Unsupported plugin platform: {args.os}/{args.arch}")

    downloads = Path("build/obs-pk-downloads")
    destination = Path("build/obs-pk-deps")
    downloads.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    for name, expected_hash in archives.items():
        archive = downloads / name
        if not archive.exists():
            url = f"https://github.com/obsproject/obs-deps/releases/download/2022-08-02/{name}"
            print(f"Downloading {url}", flush=True)
            urllib.request.urlretrieve(url, archive)
        with archive.open("rb") as stream:
            actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(f"SHA256 mismatch for {archive}: {actual_hash}")
        print(f"Extracting verified {name}", flush=True)
        if args.os == "Windows":
            with zipfile.ZipFile(archive) as package:
                package.extractall(destination)
        else:
            # Preserve the relative symlinks in the Qt frameworks.
            subprocess.run(
                ["/usr/bin/tar", "-xf", str(archive), "-C", str(destination)],
                check=True)


if __name__ == "__main__":
    main()
