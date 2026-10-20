#!/bin/bash
set -euo pipefail

: "${PACKER_DIR:?Missing PACKER_DIR}"
: "${APP_VERSION:?Missing APP_VERSION}"
: "${MACOS_SIGN_IDENTITY:?Missing signing identity}"
: "${MACOS_KEYCHAIN_PATH:?Missing temporary keychain}"

MAC_BUNDLE="$PACKER_DIR/tools/StartLive.app"
MAC_OUTPUT="$PACKER_DIR/Releases"
WIN_OUTPUT="$PACKER_DIR/Releases-win"
export PACKER_DIR APP_VERSION

test "$(cat "$PACKER_DIR/version")" = "$APP_VERSION"
test -x "$MAC_BUNDLE/Contents/MacOS/StartLive"
test -f "$PACKER_DIR/tools-win/StartLive.exe"
test -f "$PACKER_DIR/icon_left_macOS.icns"
test -f "$PACKER_DIR/icon_left.ico"

# All resource/plist changes precede signing, just as in the local packer.
python - <<'PY'
import os
from pathlib import Path
import plistlib

root = Path(os.environ["PACKER_DIR"])
bundle = root / "tools/StartLive.app"
path = bundle / "Contents/Info.plist"
info = plistlib.loads(path.read_bytes())
info.update(
    CFBundleExecutable="StartLive",
    CFBundleName="StartLive",
    CFBundleDisplayName="StartLive",
    CFBundleDevelopmentRegion="en",
    CFBundlePackageType="APPL",
    LSHasLocalizedDisplayName=True,
)
path.write_bytes(plistlib.dumps(info))
resources = bundle / "Contents/Resources"
resources.mkdir(parents=True, exist_ok=True)
for language, name in (("en", "StartLive"), ("zh-Hans", "StartLive开播器")):
    folder = resources / f"{language}.lproj"
    folder.mkdir(exist_ok=True)
    (folder / "InfoPlist.strings").write_text(
        f'"CFBundleDisplayName" = "{name}";\n"CFBundleName" = "{name}";\n'
    )
PY
plutil -lint "$MAC_BUNDLE/Contents/Info.plist" \
  "$MAC_BUNDLE/Contents/Resources/en.lproj/InfoPlist.strings" \
  "$MAC_BUNDLE/Contents/Resources/zh-Hans.lproj/InfoPlist.strings"

# Match the local packer: pre-sign recursively with the imported identity.
/usr/bin/codesign \
  --force \
  --deep \
  --sign "$MACOS_SIGN_IDENTITY" \
  --keychain "$MACOS_KEYCHAIN_PATH" \
  --identifier com.radekyspec.startlive \
  "$MAC_BUNDLE"

# vpk copies the app, adds UpdateMac and sq.version, THEN re-signs. This must
# remain enabled: merely signing tools/StartLive.app would leave a broken seal.
# Keep Velopack's default recursive signing, timestamp and entitlements.
vpk pack \
  --packId StartLive \
  --packVersion "$APP_VERSION" \
  --packDir "$MAC_BUNDLE" \
  --packTitle StartLive \
  --bundleId com.radekyspec.startlive \
  --outputDir "$MAC_OUTPUT" \
  --icon "$PACKER_DIR/icon_left_macOS.icns" \
  --runtime osx-arm64 \
  --channel osx \
  --noPortable \
  --signAppIdentity "$MACOS_SIGN_IDENTITY" \
  --keychain "$MACOS_KEYCHAIN_PATH"

vpk '[win]' pack \
  --packId StartLive \
  --packVersion "$APP_VERSION" \
  --packDir "$PACKER_DIR/tools-win" \
  --packTitle "StartLive开播器" \
  --outputDir "$WIN_OUTPUT" \
  --mainExe StartLive.exe \
  --icon "$PACKER_DIR/icon_left.ico" \
  --runtime win-x64 \
  --channel win \
  --noPortable
