# StartLive OBS PK Plugin

English | [简体中文](README_zh.md)

## Version 0.2: NV12 shared video

Update the plugin and StartLive together. SLPK v2 uses a new endpoint; v1 raw
BGRA packets are intentionally not accepted. BGRA remains an explicit pixel
format fallback within v2, not a second legacy transport implementation.

Video stays uncompressed. The plugin copies OBS Y and UV planes into one
reusable shared-memory mailbox. Windows uses a same-user file mapping and
mutex; Linux/macOS use POSIX shared memory and a named semaphore. A busy
mailbox drops the new capture instead of blocking OBS. Each connection has a
fresh random identifier; POSIX names are unlinked after attachment and live
handles keep the session alive until close. A crash before attachment can
leave a named POSIX shared-memory object (reserved capacity about 31.6 MiB)
and semaphore until reboot; neither is reused by a new session. Normal
disconnects clean up both objects.

The existing pipe/socket carries only PCM, setup and 44-byte video notices.
Its send buffer is now 16 KiB, preventing the former 1 MiB video buffer from
accumulating seconds of PCM. OS buffering is additional to the bounded audio
queues, and the effective socket buffer size is OS dependent.

The receiver snapshots under the OS lock into a pool of at most six owned
buffers. Memoryview consumers retain their buffer until the last view is
released. Preview conversion runs off the UI thread: the main preview crops
the original frame first, then scales to the display's physical pixel size,
including fractional and integer DPI scaling. Only the crop selector uses a
separate whole-frame thumbnail; crop coordinates still refer to the full OBS
frame. The existing 1000x800,
30 fps, bitrate, encoder selection, presets and crop policy are unchanged.
BT.601/709 and full/limited range travel with the pixels and into the encoder.
HDR is rejected explicitly until an SDR tone-mapping path is available.

Capture uses the OBS **output resolution**, up to **3840x2160**, at a maximum
of **30 fps** with the current build configuration. Even dimensions use NV12;
odd dimensions or failed NV12 capture initialization use BGRA over the same
shared-memory protocol. Use SDR BT.601/709 output; HDR capture is unsupported.
The OBS capture dimensions are separate from StartLive's default encoded
output of **1000x800, 30 fps, 5000 kbps**. Cropping remains in source-frame
coordinates, regardless of the preview thumbnail size.

Send OBS program video and mixed audio to StartLive over local IPC for preview,
PK encoding and transport. StartLive handles accounts, broadcasts and PK
sessions.

## Dependencies

### Building and running the plugin

All platforms require:

- **CMake 3.28 or newer** and a **C++17** compiler.
- An OBS SDK compatible with the target OBS **version, architecture and
  toolchain**,
  including headers, link libraries and CMake packages.
- Both the `libobs` and `obs-frontend-api` packages, exporting
  `OBS::libobs` and `OBS::obs-frontend-api`, respectively.
- Qt 6 development files with `Qt6::Widgets`, matching the Qt runtime used by
  OBS. The plugin uses Qt to update its capture-status menu text. StartLive's
  Python/PySide installation does not supply this C++ SDK. At runtime the
  plugin uses OBS's existing Qt libraries.
- The full StartLive source tree. CMake reads the frame-rate setting from
  `startlive/core/pk/states/encoder.py`.

| Platform             | Build tools                                                                                                | Runtime requirements                                                                    |
|----------------------|------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Windows x64          | Visual Studio / Build Tools with Desktop development with C++, a compatible MSVC toolchain and Windows SDK | Matching OBS and Visual C++ runtime; Windows supplies `advapi32`                        |
| macOS arm64 / x86_64 | Full Xcode, Apple Clang and macOS SDK; the commands below use the Xcode generator                          | Matching OBS architecture; OS minimum and deployment target compatible with the OBS SDK |
| Linux                | GCC or Clang, C++ development environment, Ninja and POSIX threads                                         | Native OBS installation, its shared libraries and a working graphics backend            |

Install the dependencies exported by the OBS SDK, including `w32-pthreads`
on Windows. Source-build dependencies are listed in the platform recipes below.

### Preparing the OBS SDK

The SDK includes `libobsConfig.cmake`, `obs-frontend-apiConfig.cmake` and the
headers and
libraries referenced by those packages.

#### Download locations

| Platform / content                           | Download location                                                                                                                | What to use                                                                                                                                        |
|----------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| OBS source for Windows / macOS               | [Official OBS Releases](https://github.com/obsproject/obs-studio/releases)                                                       | Open the matching OBS version, expand **Assets**, download `OBS-Studio-<version>-Sources.tar.gz`, then build and export the SDK as described below |
| Third-party dependencies for Windows / macOS | [Official obs-deps Releases](https://github.com/obsproject/obs-deps/releases)                                                    | Select the dependency version specified by that OBS source tree's `buildspec.json` and the target architecture for building OBS                    |
| Debian / Ubuntu development packages         | [Debian libobs-dev](https://packages.debian.org/trixie/libobs-dev) / [Ubuntu libobs-dev](https://packages.ubuntu.com/libobs-dev) | Install development files from the same distribution repositories as the OBS runtime                                                               |
| Fedora development package                   | [Fedora obs-studio-devel](https://packages.fedoraproject.org/pkgs/obs-studio/obs-studio-devel/)                                  | Install the matching development package through the distribution package manager                                                                  |

For example, for **OBS 31.1.2**, open
its [release page](https://github.com/obsproject/obs-studio/releases/tag/31.1.2)
or download
the [official source archive](https://github.com/obsproject/obs-studio/releases/download/31.1.2/OBS-Studio-31.1.2-Sources.tar.gz).
The source-build recipes below fetch this release and its submodules with Git,
then export the SDK.

For native Linux distribution packages:

```sh
# Debian / Ubuntu
sudo apt update
sudo apt install libobs-dev

# Fedora
sudo dnf install obs-studio-devel
```

Choose the commands for your distribution and development packages from the
same source and version as the OBS runtime. Both `libobs` and `obs-frontend-api`
CMake packages are required. The source-build recipes below export both
packages.

#### Building an SDK from source

The following commands target **OBS 31.1.2** and export the SDK.
Use an OBS 31.1.2 runtime of the same architecture for installation and testing.
Other OBS releases can change presets, dependencies and export paths; check
their tagged source before adapting these commands.

Start in the **StartLive repository root**. Each recipe clones OBS into a new
`build/obs-sdk-src-31.1.2` directory. Use a separate build directory for each
OBS version, architecture and generator.

These commands disable the OBS UI, application frontend, bundled plugins,
scripting and browser source. In this release, `ENABLE_FRONTEND=OFF` still
builds the frontend API. Building `libobs` and `obs-frontend-api`, then
installing
the `Development` component, exports the headers, libraries and CMake packages
needed by this plugin.

##### Windows x64

Install **Visual Studio 2022 Build Tools**, the **v143 C++ toolchain**, **ATL**,
**Windows SDK 10.0.22621**, **CMake 3.28+** and Git. On a Windows machine with
[WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/),
run the following in PowerShell and allow installer elevation when requested:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Kitware.CMake -e --source winget
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --source winget --override "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --add Microsoft.VisualStudio.Component.VC.ATL --add Microsoft.VisualStudio.Component.Windows11SDK.22621"
```

After installation, restart PowerShell so Git and CMake are on `PATH`, return
to the StartLive repository root, and run the entire block below. The official
preset downloads its pinned dependency archives into the OBS source tree's
`.deps` directory, including obs-deps and Qt. Keep network access available
during configuration.

```powershell
$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path
$ObsVersion = "31.1.2"
$ObsSource = Join-Path $RepoRoot "build/obs-sdk-src-$ObsVersion"
$ObsSdk = Join-Path $RepoRoot "build/obs-sdk-$ObsVersion-windows-x64"
New-Item -ItemType Directory -Force (Join-Path $RepoRoot "build") | Out-Null

git clone --branch $ObsVersion --recursive https://github.com/obsproject/obs-studio.git $ObsSource
if ($LASTEXITCODE -ne 0) { throw "OBS checkout failed" }

Push-Location $ObsSource
try {
    cmake --preset windows-x64 -DENABLE_UI=OFF -DENABLE_FRONTEND=OFF -DENABLE_PLUGINS=OFF -DENABLE_SCRIPTING=OFF -DENABLE_BROWSER=OFF "-DCMAKE_INSTALL_PREFIX=$ObsSdk"
    if ($LASTEXITCODE -ne 0) { throw "OBS configure failed" }
    cmake --build build_x64 --config Release --target libobs obs-frontend-api --parallel
    if ($LASTEXITCODE -ne 0) { throw "OBS SDK build failed" }
    cmake --install build_x64 --config Release --component Development --prefix $ObsSdk
    if ($LASTEXITCODE -ne 0) { throw "OBS SDK install failed" }
} finally {
    Pop-Location
}

foreach ($Package in @("libobs", "obs-frontend-api", "w32-pthreads")) {
    if (-not (Test-Path "$ObsSdk/cmake/${Package}Config.cmake")) {
        throw "Missing SDK package: $Package"
    }
}
```

The SDK is exported to `build/obs-sdk-31.1.2-windows-x64`. Its `cmake`
directory contains all three package configurations checked above.

##### macOS arm64 / x86_64

Install **full Xcode 16 or newer with macOS SDK 15 or newer** from
[Apple's Xcode downloads](https://developer.apple.com/xcode/resources/), and
install [Homebrew](https://brew.sh/). With Xcode installed at
`/Applications/Xcode.app`, initialize it and install CMake 3.28+ and Git:

```sh
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -runFirstLaunch
xcodebuild -version
xcrun --sdk macosx --show-sdk-platform-version
brew install cmake git
```

Run the next block from the StartLive repository root in a native Terminal
session. It selects the machine's architecture (`arm64` or `x86_64`); use an
OBS runtime with the same architecture. The official preset downloads its
pinned obs-deps and Qt archives into `.deps`. The deployment target is macOS
12.0, while the build machine must support the Xcode and SDK versions above.
`OBS_CODESIGN_IDENTITY=-` selects ad hoc signing for the local SDK build.

```sh
set -eu
REPO_ROOT="$PWD"
OBS_VERSION="31.1.2"
PK_ARCH="$(uname -m)"
OBS_SRC="$REPO_ROOT/build/obs-sdk-src-$OBS_VERSION"
OBS_SDK="$REPO_ROOT/build/obs-sdk-$OBS_VERSION-macos-$PK_ARCH"
mkdir -p "$REPO_ROOT/build"

git clone --branch "$OBS_VERSION" --recursive \
  https://github.com/obsproject/obs-studio.git "$OBS_SRC"

(
  cd "$OBS_SRC"
  cmake --preset macos "-DCMAKE_OSX_ARCHITECTURES=$PK_ARCH" \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0 -DOBS_CODESIGN_IDENTITY=- \
    -DENABLE_UI=OFF -DENABLE_FRONTEND=OFF -DENABLE_PLUGINS=OFF \
    -DENABLE_SCRIPTING=OFF -DENABLE_BROWSER=OFF \
    "-DCMAKE_INSTALL_PREFIX=$OBS_SDK"
)
cmake --build "$OBS_SRC/build_macos" --config Release \
  --target libobs obs-frontend-api --parallel
cmake --install "$OBS_SRC/build_macos" --config Release \
  --component Development --prefix "$OBS_SDK"

test -f "$OBS_SDK/Frameworks/libobs.framework/Resources/cmake/libobsConfig.cmake"
test -f "$OBS_SDK/lib/cmake/obs-frontend-api/obs-frontend-apiConfig.cmake"
```

The SDK is exported to `build/obs-sdk-31.1.2-macos-arm64` or
`build/obs-sdk-31.1.2-macos-x86_64`. The explicit package paths above account
for libobs being exported as a framework and the frontend API as a library.

##### Linux — Ubuntu 24.04 LTS

The following package names and commands target **Ubuntu 24.04 LTS**. They
install CMake 3.28+, GCC, Ninja, FFmpeg 6.1 development files, and dependencies
for libobs, X11, Wayland, OpenGL/EGL and PulseAudio. Other distributions need
equivalent packages with FFmpeg 6.1 or newer.

```sh
sudo apt update
sudo apt install --no-install-recommends \
  git ca-certificates build-essential cmake ninja-build pkg-config extra-cmake-modules \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev \
  libjansson-dev uthash-dev zlib1g-dev uuid-dev libglib2.0-dev \
  libx11-dev libx11-xcb-dev libxcb1-dev libxcb-xinput-dev \
  libwayland-dev libxkbcommon-dev libdrm-dev libegl-dev libgl-dev libpulse-dev qt6-base-dev
cmake --version
pkg-config --modversion libavformat
```

Return to the StartLive repository root and run:

```sh
set -eu
REPO_ROOT="$PWD"
OBS_VERSION="31.1.2"
OBS_SRC="$REPO_ROOT/build/obs-sdk-src-$OBS_VERSION"
OBS_BUILD="$OBS_SRC/build_sdk"
OBS_SDK="$REPO_ROOT/build/obs-sdk-$OBS_VERSION-linux"
mkdir -p "$REPO_ROOT/build"

git clone --branch "$OBS_VERSION" --recursive \
  https://github.com/obsproject/obs-studio.git "$OBS_SRC"

cmake -S "$OBS_SRC" -B "$OBS_BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_LIBDIR=lib \
  "-DCMAKE_INSTALL_PREFIX=$OBS_SDK" \
  -DENABLE_UI=OFF -DENABLE_FRONTEND=OFF -DENABLE_PLUGINS=OFF \
  -DENABLE_SCRIPTING=OFF -DENABLE_BROWSER=OFF
cmake --build "$OBS_BUILD" --target libobs obs-frontend-api --parallel
cmake --install "$OBS_BUILD" --config Release \
  --component Development --prefix "$OBS_SDK"

test -f "$OBS_SDK/lib/cmake/libobs/libobsConfig.cmake"
test -f "$OBS_SDK/lib/cmake/obs-frontend-api/obs-frontend-apiConfig.cmake"
```

The SDK is exported to `build/obs-sdk-31.1.2-linux`, with both CMake packages
under `lib/cmake`. Run the SDK build and export commands as your regular user.

##### Using the generated SDK

Continue with the plugin build and installation section for your platform.
The commands use the SDK paths generated above. For an SDK installed elsewhere,
set `ObsSdk` / `OBS_SDK` to its installation prefix.

Keep the OBS source, build directory and downloaded dependencies available
during development. The `Development` component provides compilation files.
Install OBS separately to supply the application, runtime libraries and graphics
modules used for plugin loading and capture.

The version-specific details above follow the OBS 31.1.2
[build presets](https://github.com/obsproject/obs-studio/blob/31.1.2/CMakePresets.json),
[frontend API configuration](https://github.com/obsproject/obs-studio/blob/31.1.2/frontend/CMakeLists.txt)
and [SDK export rules](https://github.com/obsproject/obs-studio/blob/31.1.2/cmake/common/helpers_common.cmake).

### StartLive runtime dependencies

Local preview and RTC integration use the StartLive Python environment:

- Python **3.11–3.14**.
- Application dependencies from `requirements.txt`, including PySide6.
- The PK extra, currently pinning `aiortc==1.15.0` and `aioice==0.10.2`.
  Dependencies such as PyAV are installed transitively.

Virtual-environment installation commands are provided in the verification
section.

## Before building

Run all commands from the **StartLive repository root**, using the full checkout
or a source distribution containing the plugin.

```text
StartLive/
├── plugins/obs-startlive-pk/
│   ├── CMakeLists.txt
│   └── src/
└── startlive/core/pk/states/encoder.py
```

Check `cmake --version` first. Replace the example SDK and OBS paths with your
installation paths. Use separate build directories for different platforms,
architectures or generators.
The plugin build produces only the plugin module; no test-host executables are
built.

## Windows: build and install

In PowerShell, configure and build with Visual Studio 2022 and the exported SDK.
For another compatible Visual Studio version, select its CMake generator.

```powershell
$ObsSdk = Join-Path $PWD "build/obs-sdk-31.1.2-windows-x64"
$QtSdk = Join-Path $PWD "build/obs-sdk-src-31.1.2/.deps/obs-deps-qt6-2025-07-11-x64"

cmake -S plugins/obs-startlive-pk -B build/obs-pk-windows -G "Visual Studio 17 2022" -A x64 "-DCMAKE_PREFIX_PATH=$ObsSdk;$QtSdk"
if ($LASTEXITCODE -ne 0) { throw "Plugin configure failed" }
cmake --build build/obs-pk-windows --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed" }
```

Close OBS, then install into the OBS directory you use. Set `ObsRoot` to the
installed or portable OBS directory. Use an administrator PowerShell session
when installing into Program Files, starting from the StartLive repository root.

```powershell
$ObsRoot = "C:/Program Files/obs-studio"
cmake --install build/obs-pk-windows --config Release --prefix "$ObsRoot"
```

Installed plugin: `$ObsRoot/obs-plugins/64bit/obs-startlive-pk.dll`.
Continue with **Start and verify** below.

## macOS: build and install

With Xcode initialized, run the following in Terminal. Set `PK_ARCH` to the
OBS runtime architecture (`arm64` or `x86_64`) and `OBS_SDK` to the matching
SDK.
The commands use the SDK exported above and a macOS 12.0 deployment target.

```sh
set -eu
PK_ARCH="$(uname -m)"
OBS_SDK="$PWD/build/obs-sdk-31.1.2-macos-$PK_ARCH"
QT_SDK="$PWD/build/obs-sdk-src-31.1.2/.deps/obs-deps-qt6-2025-07-11-universal"

cmake -S plugins/obs-startlive-pk -B build/obs-pk-macos -G Xcode \
  "-DCMAKE_PREFIX_PATH=$OBS_SDK;$OBS_SDK/Frameworks;$QT_SDK" \
  "-Dlibobs_DIR=$OBS_SDK/Frameworks/libobs.framework/Resources/cmake" \
  "-Dobs-frontend-api_DIR=$OBS_SDK/lib/cmake/obs-frontend-api" \
  "-DCMAKE_OSX_ARCHITECTURES=$PK_ARCH" -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0
cmake --build build/obs-pk-macos --config Release --parallel
```

Close OBS and install the plugin bundle:

```sh
cmake --install build/obs-pk-macos --config Release \
  --prefix "$HOME/Library/Application Support/obs-studio/plugins"
```

Installed plugin:
`~/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin`.
Continue with **Start and verify** below.

## Linux: build and install

For a native OBS installation, configure and build with Ninja and the exported
SDK:

```sh
set -eu
OBS_SDK="$PWD/build/obs-sdk-31.1.2-linux"

cmake -S plugins/obs-startlive-pk -B build/obs-pk-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$OBS_SDK" \
  -DCMAKE_INSTALL_LIBDIR=lib
cmake --build build/obs-pk-linux --parallel
```

Close OBS and install the compiled plugin into the current user's OBS plugin
directory:

```sh
PK_PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/obs-studio/plugins/obs-startlive-pk/bin/64bit"
install -Dm755 build/obs-pk-linux/obs-startlive-pk.so \
  "$PK_PLUGIN_DIR/obs-startlive-pk.so"
```

Installed plugin:
`${XDG_CONFIG_HOME:-$HOME/.config}/obs-studio/plugins/obs-startlive-pk/bin/64bit/obs-startlive-pk.so`.
Continue with **Start and verify** below.
Installation layouts are documented in
the [OBS plugin guide](https://obsproject.com/kb/plugins-guide).

## Start and verify

Install StartLive from the repository root.

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv-pk
& ./.venv-pk/Scripts/python.exe -m pip install --upgrade pip
& ./.venv-pk/Scripts/python.exe -m pip install -e ".[pk]"
& ./.venv-pk/Scripts/startlive.exe
```

**macOS / Linux**

```sh
python3 -m venv .venv-pk
.venv-pk/bin/python -m pip install --upgrade pip
.venv-pk/bin/python -m pip install -e ".[pk]"
.venv-pk/bin/startlive
```

Ensure `python3` is within the supported version range. The Windows example
selects Python 3.11.

1. Restart OBS after installing the plugin.
2. Choose **Tools → StartLive PK 采集：已关闭** to start capture. The label
   changes
   to **StartLive PK 采集：已开启** after capture starts and returns to **已关闭
   **
   when capture stops. A failed start leaves it closed; this indicates OBS
   capture status, not whether a StartLive client is connected.
3. Open the **PK / OBS media window** from StartLive's File menu. It connects
   automatically and displays OBS program output.
4. Route the intended outgoing audio sources to OBS track 1 and remote playback
   to a separate monitoring path. Confirm that StartLive receives video and
   audio.
5. Close the PK window to end preview. Choose the OBS menu item again to stop
   capture. Start capture and reopen the PK window to verify reconnection.
   Capture also stops when OBS exits.

Run OBS and StartLive as the same OS user. Each capture endpoint accepts one
media client. The capture toggle controls the local media connection;
StartLive handles online PK accounts, signaling and networking.

If capture does not start, check the OBS output resolution and color space,
and confirm that another OBS instance is not using the endpoint. In the OBS
log, a successful start reports
`[StartLive PK] Capture ... NV12 shared-memory v2`
or `BGRA shared-memory v2`. If capture starts but StartLive receives no frames,
check that both sides were updated, run as the same OS user, and that no other
StartLive media client is connected.
