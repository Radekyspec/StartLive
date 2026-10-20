"""Import the local packer's signing identity into a temporary CI keychain."""

import argparse
import base64
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

CERTIFICATE_NAME = "StartLive Local Signing"


def run(args, *, label):
    """Do not print argv: security commands contain passwords."""
    result = subprocess.run([str(a) for a in args], capture_output=True,
                            text=True)
    if result.returncode:
        raise ValueError(f"{label} failed (exit {result.returncode})")
    return result.stdout


def require_hosted_runner():
    if (sys.platform != "darwin" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError(
            "Keychain/trust changes are restricted to ephemeral GitHub-hosted macOS runners")


def import_identity(state):
    require_hosted_runner()
    os.umask(0o077)
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    encoded = os.environ.get("MACOS_P12_BASE64", "")
    password = os.environ.get("MACOS_P12_PASSWORD", "")
    if not encoded or not password:
        raise ValueError(
            "Missing MACOS_P12_BASE64 or MACOS_P12_PASSWORD repository secret")
    try:
        data = base64.b64decode("".join(encoded.split()), validate=True)
    except ValueError as error:
        raise ValueError("MACOS_P12_BASE64 is not valid Base64") from error
    keychain = state / "signing.keychain-db"
    old = shlex.split(run(["security", "list-keychains", "-d", "user"],
                          label="Read keychain search list"))
    (state / "search-list.json").write_text(json.dumps(old))
    keychain_password = secrets.token_urlsafe(48)
    # Keep the password out of stdout; run() captures output and reports labels only.
    run(["security", "create-keychain", "-p", keychain_password, keychain],
        label="Create temporary keychain")
    run(["security", "set-keychain-settings", "-lut", "21600", keychain],
        label="Set keychain timeout")
    run(["security", "unlock-keychain", "-p", keychain_password, keychain],
        label="Unlock temporary keychain")
    p12 = state / "identity.p12"
    try:
        p12.write_bytes(data)
        run(["security", "import", p12, "-k", keychain, "-P", password,
             "-T", "/usr/bin/codesign"],
            label="Import P12 certificate/private key")
    finally:
        p12.unlink(missing_ok=True)
    run(["security", "set-key-partition-list", "-S",
         "apple-tool:,apple:,codesign:",
         "-s", "-k", keychain_password, keychain],
        label="Allow noninteractive signing")
    run(["security", "list-keychains", "-d", "user", "-s", keychain, *old],
        label="Include temporary keychain in search list")

    identity_args = ["security", "find-identity", "-v", "-p", "codesigning",
                     keychain]
    pattern = r'^\s*\d+\)\s+([0-9A-Fa-f]{40})\s+"' + re.escape(
        CERTIFICATE_NAME) + '"'
    identities = run(identity_args, label="Find signing identity")
    if not re.search(pattern, identities, re.MULTILINE):
        # The user's local packer uses this self-signed Code Signing certificate.
        # Trust only that certificate for codeSign, on the ephemeral CI runner.
        certificate = state / "trust-anchor.pem"
        certificate.write_text(run(
            ["security", "find-certificate", "-c", CERTIFICATE_NAME, "-p",
             keychain],
            label=f"Find {CERTIFICATE_NAME} certificate",
        ))
        (state / "admin-trust-added").touch()
        run(["sudo", "-n", "security", "add-trusted-cert", "-d", "-r",
             "trustRoot",
             "-p", "codeSign", "-k", keychain, certificate],
            label="Trust signing certificate")
        identities = run(identity_args, label="Find trusted signing identity")
    fingerprints = set(re.findall(pattern, identities, re.MULTILINE))
    if len(fingerprints) != 1:
        raise ValueError(
            f"Expected one valid {CERTIFICATE_NAME} identity with its private key")
    fingerprint = fingerprints.pop()
    print(f"Using {CERTIFICATE_NAME}: {fingerprint}")
    with open(os.environ["GITHUB_ENV"], "a") as output:
        output.write(
            f"MACOS_KEYCHAIN_PATH={keychain}\nMACOS_SIGN_IDENTITY={fingerprint}\n")


def cleanup(state):
    if not state.exists():
        return
    require_hosted_runner()
    errors = []
    certificate = state / "trust-anchor.pem"
    commands = []
    if (state / "admin-trust-added").exists():
        commands.append((["sudo", "-n", "security", "remove-trusted-cert", "-d",
                          certificate], "Remove temporary Code Signing trust"))
    if (state / "search-list.json").exists():
        old = json.loads((state / "search-list.json").read_text())
        commands.append(
            (["security", "list-keychains", "-d", "user", "-s", *old],
             "Restore keychain search list"))
    keychain = state / "signing.keychain-db"
    if keychain.exists():
        commands.append((["security", "delete-keychain", keychain],
                         "Delete temporary keychain"))
    for command, label in commands:
        try:
            run(command, label=label)
        except ValueError as error:
            errors.append(str(error))
    shutil.rmtree(state)
    if errors:
        raise ValueError("; ".join(errors))
    print(
        "Temporary trust, certificate files, P12 and keychain removed; search list restored.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("import", "cleanup"))
    args = parser.parse_args()
    state = Path(os.environ["SIGNING_STATE_DIR"])
    (import_identity if args.command == "import" else cleanup)(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # In particular, never print a subprocess traceback containing secrets.
        print(f"macOS signing failed: {error}", file=sys.stderr)
        sys.exit(1)
