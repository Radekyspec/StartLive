"""Release PR versions, verified update history, and an explicit R2 upload list."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

BASE_URL = "https://startlive-soft.vtbs.ai"
CHANNELS = (("win", "Releases-win", "RELEASES"),
            ("osx", "Releases", "RELEASES-osx"))
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def version_key(version):
    """SemVer precedence, intentionally excluding build metadata."""
    match = SEMVER.fullmatch(version)
    if not match:
        raise ValueError(
            "Version must be strict SemVer, for example 1.4.0 or 1.4.0-beta.1")
    major, minor, patch, prerelease, _ = match.groups()
    labels = tuple((0, int(p)) if p.isdigit() else (1, p) for p in
                   (prerelease or "").split("."))
    return int(major), int(minor), int(patch), prerelease is None, labels


def title_version(title):
    if not title.startswith("Release-v"):
        raise ValueError("Release PR title must be exactly Release-v<SemVer>")
    version = title[len("Release-v"):]
    version_key(version)
    return version


def safe_filename(name):
    if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]*", name):
        raise ValueError("Release feed contains an unsafe filename")
    return name


def download(name, destination):
    safe_filename(name)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--proto", "=https", "--proto-redir", "=https",
            "--retry", "4", "--retry-all-errors", "--connect-timeout", "30",
            "--max-time", "900", "--header", "Cache-Control: no-cache",
            "--output", str(partial), f"{BASE_URL}/{quote(name)}",
        ], check=True)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def assets_from(path):
    data = json.loads(Path(path).read_text())
    assets = data.get("Assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError(
            f"{Path(path).name} must contain a nonempty Assets array")
    seen = set()
    for asset in assets:
        name = safe_filename(asset["FileName"])
        if name in seen or asset.get("PackageId") != "StartLive":
            raise ValueError(
                "Unexpected package ID or duplicate filename in release feed")
        seen.add(name)
        version_key(asset["Version"])
        if asset.get("Type") not in ("Full", "Delta") or not name.endswith(
                ".nupkg"):
            raise ValueError(f"Unexpected asset type for {name}")
    if not any(a["Type"] == "Full" for a in assets):
        raise ValueError(
            "The release feed has no full package to use as a delta base")
    return assets


def require_newer(version, assets):
    if any(version_key(version) <= version_key(a["Version"]) for a in assets):
        raise ValueError(
            f"Release {version} must be newer than every published version; "
            "use a new Release-v<SemVer> PR instead of overwriting a release"
        )


def verify_asset(path, asset):
    path = Path(path)
    if path.stat().st_size != asset["Size"]:
        raise ValueError(f"Size mismatch: {path.name}")
    hashes = {key: hashlib.new(key.lower()) for key in ("SHA256", "SHA1") if
              asset.get(key)}
    if not hashes:
        raise ValueError(f"Missing checksum: {path.name}")
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            for digest in hashes.values():
                digest.update(block)
    if any(digest.hexdigest().upper() != asset[key].upper() for key, digest in
           hashes.items()):
        raise ValueError(f"Checksum mismatch: {path.name}")


def check_title():
    version = title_version(os.environ["RELEASE_TITLE"])
    with tempfile.TemporaryDirectory() as tmp:
        for channel, _, _ in CHANNELS:
            path = Path(tmp) / f"releases.{channel}.json"
            download(path.name, path)
            require_newer(version, assets_from(path))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"version={version}\n")
    print(f"Release version: {version}")


def prepare(root, version):
    history = {}
    for channel, directory, legacy in CHANNELS:
        output = root / directory
        output.mkdir(parents=True, exist_ok=True)
        feed = output / f"releases.{channel}.json"
        download(feed.name, feed)
        assets = assets_from(feed)
        require_newer(version, assets)
        download(legacy, output / legacy)
        for asset in assets:
            path = output / asset["FileName"]
            print(f"Downloading {path.name}", flush=True)
            download(path.name, path)
            verify_asset(path, asset)
        history[channel] = assets
    for icon in ("icon_left_macOS.icns", "icon_left.ico"):
        download(icon, root / icon)
    (root / "previous-assets.json").write_text(json.dumps(history))


def validate(root, version):
    """Check all history survives and select only this version's full/delta."""
    previous = json.loads((root / "previous-assets.json").read_text())
    packages, feeds = [], []
    for channel, directory, legacy in CHANNELS:
        output = root / directory
        feed = output / f"releases.{channel}.json"
        assets = assets_from(feed)
        by_name = {a["FileName"]: a for a in assets}
        for old in previous[channel]:
            if old["FileName"] not in by_name:
                raise ValueError(
                    f"Historical update disappeared: {old['FileName']}")
            verify_asset(output / old["FileName"], old)
        current = [a for a in assets if
                   version_key(a["Version"]) == version_key(version)]
        if sorted(a["Type"] for a in current) != ["Delta", "Full"]:
            raise ValueError(
                f"{channel}: expected exactly one new full and one new delta")
        for asset in assets:
            verify_asset(output / asset["FileName"], asset)
        packages.extend(f"{directory}/{a['FileName']}" for a in current)
        legacy_path = output / legacy
        if not legacy_path.is_file():
            raise ValueError(f"Missing legacy update feed: {legacy}")
        # Velopack's legacy Squirrel format excludes versions containing dotted
        # prerelease labels or build metadata. The JSON feed retains all versions.
        legacy_entries = {}
        for line in legacy_path.read_text().splitlines():
            sha1, name, size = line.split()
            legacy_entries[name] = (sha1.upper(), int(size))
        for asset in assets:
            match = SEMVER.fullmatch(asset["Version"])
            if asset["Type"] == "Full" and not match[5] and "." not in (
                    match[4] or ""):
                expected = (asset["SHA1"].upper(), asset["Size"])
                if legacy_entries.get(asset["FileName"]) != expected:
                    raise ValueError(f"Incomplete legacy feed: {legacy}")
        feeds.extend((f"{directory}/{legacy}", f"{directory}/{feed.name}"))
    for installer in ("Releases/StartLive-osx-Setup.pkg",
                      "Releases-win/StartLive-win-Setup.exe"):
        if not (root / installer).is_file() or (
                root / installer).stat().st_size == 0:
            raise ValueError(f"Missing installer: {installer}")
    # Publish payloads first and pointers last. Never recursively sync the folder.
    result = {"version": version, "packages": packages, "feeds": feeds}
    (root / "r2-upload.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Validated release files:\n" + "\n".join(packages + feeds))
    return result


def publish(root, version):
    plan = validate(root, version)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                 "R2_ENDPOINT_URL", "R2_BUCKET"):
        if not os.environ.get(name):
            raise ValueError(f"Missing GitHub Actions secret for {name}")
    endpoint = os.environ["R2_ENDPOINT_URL"]
    parsed = urlparse(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".r2.cloudflarestorage.com")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError(
            "R2_ENDPOINT_URL must be the bucket's HTTPS R2 S3 API endpoint")
    bucket = os.environ["R2_BUCKET"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Invalid R2_BUCKET")
    for category in ("packages", "feeds"):
        for relative in plan[category]:
            path = root / relative
            args = [
                "aws", "s3", "cp", str(path), f"s3://{bucket}/{path.name}",
                "--endpoint-url", endpoint, "--region", "auto",
                "--only-show-errors",
                "--cache-control",
                "no-cache" if category == "feeds" else "public,max-age=31536000,immutable",
            ]
            if path.suffix == ".json":
                args += ["--content-type", "application/json"]
            elif category == "feeds":
                args += ["--content-type", "text/plain"]
            # Avoid including credentials/endpoint in a CalledProcessError traceback.
            if subprocess.run(args).returncode:
                raise ValueError(
                    f"R2 upload failed for {path.name}; update feeds are uploaded after packages")
            print(f"Uploaded {path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=("version", "prepare", "validate", "publish"))
    parser.add_argument("root", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "version":
        check_title()
    else:
        if args.root is None:
            parser.error("root is required")
        version = os.environ["APP_VERSION"]
        version_key(version)
        globals()[args.command](args.root, version)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError,
            subprocess.CalledProcessError) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        sys.exit(1)
