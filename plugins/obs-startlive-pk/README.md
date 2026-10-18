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

Release builds use **OBS 28.0.0**, **Qt 6.3.1** and the official
**obs-deps 2022-08-02** archives. See the pinned
[OBS 28 workflow](https://github.com/obsproject/obs-studio/blob/28.0.0/.github/workflows/main.yml)
and [dependency release](https://github.com/obsproject/obs-deps/releases/tag/2022-08-02).
Downloads are checked against SHA256 before extraction.

The goal is compatibility with OBS 28 and newer on the same architecture.
Building with the oldest supported public OBS/Qt APIs avoids requiring newer
symbols. This is not a guarantee for every future OBS version: test loading,
menu updates, audio/video capture and reconnection on each supported release.
OBS 27 and Qt 5 builds are outside this baseline.

| Platform            | CI runner / tools                                                                            | Plugin runtime minimum                              |
|---------------------|----------------------------------------------------------------------------------------------|-----------------------------------------------------|
| Windows x64         | `windows-2025-vs2026`, VS 2026 generator, **v142 14.29.30133**, Windows SDK **10.0.26100.0** | Windows 10; OBS 28+ x64 and compatible VC++ runtime |
| macOS Intel         | `macos-15-intel`, **Xcode 16.4**, macOS SDK **15.5**                                         | macOS **10.15**, OBS 28+ x86_64                     |
| macOS Apple Silicon | `macos-15`, **Xcode 16.4**, macOS SDK **15.5**                                               | macOS **11.0**, OBS 28+ arm64                       |

CMake is pinned to **4.2.3**. These runners already contain the specified
MSVC toolset / Windows SDK or Xcode; CI does not install another VS or Xcode.
The latest MSVC cannot compile Qt 6.3.1's `stdext` references, so the plugin
explicitly selects v142. Nuitka continues to use the runner's current MSVC.
These are plugin requirements; StartLive's Python/PySide dependencies can
require a newer operating system.
The Windows API target is Windows 10; Qt 6.3's officially tested Windows 10
configuration is 21H2 or later, so support for every earlier Windows 10 build
is not implied.

Run from the StartLive repository root, using fresh build directories:

```sh
python -m pip install cmake==4.2.3
git clone --branch 28.0.0 --depth 1 https://github.com/obsproject/obs-studio.git build/obs-sdk-source
```

#### Windows SDK

Locally, install VS 2026 with the v142 x64 tools and Windows SDK 10.0.26100.0.
Set `VsRoot` to your installation; the example matches the CI Enterprise path.

```powershell
python tools/prepare_obs_pk_deps.py --os Windows --arch X64
$ObsSource = "$PWD/build/obs-sdk-source"
$ObsBuild = "$PWD/build/obs-sdk-build"
$ObsSdk = "$PWD/build/obs-sdk"
$ObsDeps = "$PWD/build/obs-pk-deps"
$VsRoot = "$env:ProgramFiles/Microsoft Visual Studio/18/Enterprise"
$VsArgs = @('-G', 'Visual Studio 18 2026', '-A', 'x64,version=10.0.26100.0',
            '-T', 'v142,version=14.29.30133,host=x64', "-DCMAKE_GENERATOR_INSTANCE=$VsRoot")
python -m cmake -S $ObsSource -B $ObsBuild @VsArgs `
  "-DOBS_VERSION_OVERRIDE=28.0.0" "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" `
  -DENABLE_UI=OFF -DENABLE_PLUGINS=OFF -DENABLE_SCRIPTING=OFF `
  "-DCMAKE_PREFIX_PATH=$ObsDeps" "-DCMAKE_INSTALL_PREFIX=$ObsSdk"
if ($LASTEXITCODE -ne 0) { throw 'OBS configure failed' }
python -m cmake --build $ObsBuild --config Release --target libobs obs-frontend-api --parallel
if ($LASTEXITCODE -ne 0) { throw 'OBS build failed' }
python -m cmake --install $ObsBuild --config Release --component obs_libraries --prefix $ObsSdk
if ($LASTEXITCODE -ne 0) { throw 'OBS install failed' }
```

#### macOS SDK

Install full Xcode 16.4. The example selects Apple Silicon; on Intel change
all three architecture/target values as indicated. OBS 28 exports the
`obs_libraries` component, and its macOS export omits the public frontend
header; the final command copies that exact header from the pinned source.

```sh
set -eu
export DEVELOPER_DIR=/Applications/Xcode_16.4.app/Contents/Developer
# Intel: X64 / x86_64 / 10.15; Apple Silicon: ARM64 / arm64 / 11.0
python tools/prepare_obs_pk_deps.py --os macOS --arch ARM64
PK_ARCH=arm64
PK_MACOS_TARGET=11.0
OBS_SRC="$PWD/build/obs-sdk-source"
OBS_BUILD="$PWD/build/obs-sdk-build"
OBS_SDK="$PWD/build/obs-sdk"
OBS_DEPS="$PWD/build/obs-pk-deps"
python -m cmake -S "$OBS_SRC" -B "$OBS_BUILD" -G Xcode \
  -DOBS_VERSION_OVERRIDE=28.0.0 -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  "-DCMAKE_OSX_ARCHITECTURES=$PK_ARCH" "-DCMAKE_OSX_DEPLOYMENT_TARGET=$PK_MACOS_TARGET" \
  -DCMAKE_OSX_SYSROOT=macosx15.5 -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
  -DOBS_CODESIGN_LINKER=OFF \
  -DENABLE_UI=OFF -DENABLE_PLUGINS=OFF -DENABLE_SCRIPTING=OFF \
  "-DCMAKE_PREFIX_PATH=$OBS_DEPS" "-DCMAKE_INSTALL_PREFIX=$OBS_SDK"
python -m cmake --build "$OBS_BUILD" --config Release --target libobs obs-frontend-api --parallel
python -m cmake --install "$OBS_BUILD" --config Release --component obs_libraries --prefix "$OBS_SDK"
install -m 644 "$OBS_SRC/UI/obs-frontend-api/obs-frontend-api.h" "$OBS_SDK/include/obs/obs-frontend-api.h"
```

The SDK lives in `build/obs-sdk`; Qt and native build dependencies live in
`build/obs-pk-deps`. Neither the rebuilt OBS libraries nor this Qt runtime is
shipped with the plugin: it links to the host OBS's libraries at runtime.
The complete CI steps are maintained in the
[shared build action](../../.github/actions/build-obs-pk/action.yml).

On macOS, the deployment target controls the minimum runtime OS; the selected
SDK controls compilation. Intermediate SDK/plugin signing is disabled, then
the packaged plugin and app receive ad hoc signatures. The `.plugin` bundle
layout and OBS framework RPATH remain in place. Qt 6.3.1's OpenGL wrapper is
linked through `OpenGL::GL` to fix its handling of modern CMake framework paths
and omit the unused 64-bit AGL framework; OpenGL functionality is retained.

#### Linux SDK

Linux is not in the release CI matrix. For a local build, install the OBS 28+
development packages and Qt 6 development files matching the native OBS
installation (for example `libobs-dev` and `qt6-base-dev` on Debian/Ubuntu,
or `obs-studio-devel` and `qt6-qtbase-devel` on Fedora). Both `libobs` and
`obs-frontend-api` CMake packages are required. Distribution builds are tied
to their own library versions; they do not inherit the Windows/macOS binary
compatibility baseline.

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

In PowerShell, configure and build with Visual Studio 2026 + v142 and the
exported SDK.
Reuse `VsArgs` from the Windows SDK commands above.

```powershell
$ObsSdk = Join-Path $PWD "build/obs-sdk"
$QtSdk = Join-Path $PWD "build/obs-pk-deps"

python -m cmake -S plugins/obs-startlive-pk -B build/obs-pk-windows @VsArgs "-DCMAKE_PREFIX_PATH=$ObsSdk;$QtSdk"
if ($LASTEXITCODE -ne 0) { throw "Plugin configure failed" }
python -m cmake --build build/obs-pk-windows --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed" }
```

Close OBS, then install into the OBS directory you use. Set `ObsRoot` to the
installed or portable OBS directory. Use an administrator PowerShell session
when installing into Program Files, starting from the StartLive repository root.

```powershell
$ObsRoot = "C:/Program Files/obs-studio"
python -m cmake --install build/obs-pk-windows --config Release --prefix "$ObsRoot"
```

Installed plugin: `$ObsRoot/obs-plugins/64bit/obs-startlive-pk.dll`.
Continue with **Start and verify** below.

## macOS: build and install

With Xcode initialized, run the following in Terminal. Set `PK_ARCH` to the
OBS runtime architecture (`arm64` or `x86_64`) and `OBS_SDK` to the matching
SDK.
The commands use the SDK exported above and a macOS 11.0 deployment target (
Intel: 10.15).

```sh
set -eu
PK_ARCH=arm64
PK_MACOS_TARGET=11.0
export DEVELOPER_DIR=/Applications/Xcode_16.4.app/Contents/Developer
OBS_SDK="$PWD/build/obs-sdk"
QT_SDK="$PWD/build/obs-pk-deps"

python -m cmake -S plugins/obs-startlive-pk -B build/obs-pk-macos -G Xcode \
  -DCMAKE_OSX_SYSROOT=macosx15.5 \
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
  "-DCMAKE_PREFIX_PATH=$OBS_SDK;$OBS_SDK/Frameworks;$QT_SDK" \
  "-Dlibobs_DIR=$OBS_SDK/Frameworks/libobs.framework/Resources/cmake" \
  "-Dobs-frontend-api_DIR=$OBS_SDK/lib/cmake/obs-frontend-api" \
  "-DCMAKE_OSX_ARCHITECTURES=$PK_ARCH" "-DCMAKE_OSX_DEPLOYMENT_TARGET=$PK_MACOS_TARGET"
python -m cmake --build build/obs-pk-macos --config Release --parallel
```

Close OBS and install the plugin bundle:

```sh
python -m cmake --install build/obs-pk-macos --config Release \
  --prefix "$HOME/Library/Application Support/obs-studio/plugins"
codesign --force --sign - --timestamp=none \
  "$HOME/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin"
```

Installed plugin:
`~/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin`.
Continue with **Start and verify** below.

## Linux: build and install

For a native OBS installation, configure and build with Ninja and the
distribution's OBS/Qt development packages:

```sh
set -eu

cmake -S plugins/obs-startlive-pk -B build/obs-pk-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
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
