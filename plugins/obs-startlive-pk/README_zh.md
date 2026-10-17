# StartLive OBS PK 插件

[English](README.md) | 简体中文

## 0.2 版本：NV12 共享内存

本版使用 SLPK v2 新端点，移除了生产代码中的
v1 BGRA 大包传输。BGRA 仍作为 v2 内明确标识的像素格式回退。

视频保持未压缩，OBS 直接写入可复用的共享帧区；管道或套接字只传 PCM、
初始化信息和小型帧通知。Windows 使用当前用户可访问的内存映射与互斥量，
Linux/macOS 使用 POSIX 共享内存与信号量。读写冲突时丢弃新帧，不等待消费者。

接收端最多复用六个自有缓冲，最后一个引用释放后才复用，预览与编码不会读取
被覆盖的共享帧。NV12 主预览在后台先裁剪原始帧，再按显示区域的实际像素尺寸转换，
适配整数与小数 DPI 缩放；裁剪选择器单独使用整帧缩略图，裁剪坐标仍对应完整原始画面。
现有 1000×800、30 fps、码率、编码器选择、预设与裁剪策略保持不变。
明确传递 BT.601/709 和完整/有限范围；HDR 在实现色调映射前会拒绝启动。

插件采集 OBS 的**输出分辨率**，最大 **3840×2160**，当前构建配置最高 **30 fps**。
偶数尺寸优先使用 NV12；奇数尺寸或 NV12 捕获初始化失败时，通过同一共享内存协议
回退为 BGRA。OBS 请使用 SDR BT.601/709 输出，暂不支持 HDR 采集。
采集尺寸与 StartLive 默认的 **1000×800、30 fps、5000 kbps** 编码输出分别处理；
裁剪仍使用原始画面坐标，不受预览缩略图尺寸影响。

每次连接创建新的共享对象。正常断线会清理对象；POSIX 接收端附着后即移除对象名称，
最后一个句柄关闭后释放资源。若 OBS 在创建对象后、接收端附着前崩溃，可能留下预留
约 31.6 MiB 的命名共享内存和信号量直至系统重启；新会话不会复用这些旧对象。

将 OBS 的节目画面与混音通过本机 IPC 传给 StartLive，用于媒体预览及 PK
编码、传输。账号、直播和 PK 会话由 StartLive 管理。

## 依赖

### 编译与运行插件

所有平台均需要：

- **CMake 3.28 或更新版本**和支持 **C++17** 的编译器。
- 与目标 OBS **版本、架构、工具链兼容的 OBS SDK**，包括头文件、链接库和 CMake
  package。
- SDK 必须提供 `libobs`、`obs-frontend-api` 两个 package，分别导出 `OBS::libobs`、
  `OBS::obs-frontend-api`。
- 与 OBS 使用的 Qt 运行库匹配的 Qt 6 开发文件，提供 `Qt6::Widgets`。
  插件通过 Qt 更新采集状态菜单；StartLive 的 Python/PySide 安装不能代替此 C++
  SDK。
  运行时复用 OBS 自带的 Qt 库。
- 完整 StartLive 源码目录。CMake 会读取 `startlive/core/pk/states/encoder.py`
  中的帧率配置。

| 平台                   | 编译工具                                                                  | 运行依赖                                  |
|----------------------|-----------------------------------------------------------------------|---------------------------------------|
| Windows x64          | Visual Studio / Build Tools 的“使用 C++ 的桌面开发”、兼容 SDK 的 MSVC、Windows SDK | 同架构 OBS、对应 Visual C++ 运行库             |
| macOS arm64 / x86_64 | 完整 Xcode、Apple Clang、macOS SDK；下文使用 Xcode 生成器                         | 同架构 OBS；最低 macOS 版本与部署目标应匹配所选 OBS SDK |
| Linux                | GCC 或 Clang、C++ 开发环境、Ninja、POSIX 线程支持                                 | 原生安装的 OBS、其共享库和可用的图形后端                |

### 准备 OBS SDK

SDK 应包含 `libobsConfig.cmake`、`obs-frontend-apiConfig.cmake` 及其引用的头文件和库。

#### 下载入口

| 平台 / 内容                  | 下载位置                                                                                                                             | 如何使用                                                                           |
|--------------------------|----------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| Windows / macOS 的 OBS 源码 | [OBS 官方 Releases](https://github.com/obsproject/obs-studio/releases)                                                             | 打开与目标 OBS 一致的版本，展开 **Assets**，下载 `OBS-Studio-<版本>-Sources.tar.gz`，按下文编译并导出 SDK |
| Windows / macOS 的第三方依赖   | [obs-deps 官方 Releases](https://github.com/obsproject/obs-deps/releases)                                                          | 选择对应 OBS 源码 `buildspec.json` 指定的依赖版本及目标架构，用于构建 OBS                             |
| Debian / Ubuntu 开发包      | [Debian libobs-dev](https://packages.debian.org/trixie/libobs-dev) / [Ubuntu libobs-dev](https://packages.ubuntu.com/libobs-dev) | 从与已安装 OBS 相同的发行版软件源安装开发包                                                       |
| Fedora 开发包               | [Fedora obs-studio-devel](https://packages.fedoraproject.org/pkgs/obs-studio/obs-studio-devel/)                                  | 通过发行版包管理器安装与运行时匹配的开发包                                                          |

例如，目标 OBS 为 **31.1.2**
时，可从 [31.1.2 发布页](https://github.com/obsproject/obs-studio/releases/tag/31.1.2)
下载 [官方源码包](https://github.com/obsproject/obs-studio/releases/download/31.1.2/OBS-Studio-31.1.2-Sources.tar.gz)
。下方源码构建步骤使用 Git 获取此版本及子模块，再导出 SDK。

Linux 原生软件源安装示例：

```sh
# Debian / Ubuntu
sudo apt update
sudo apt install libobs-dev

# Fedora
sudo dnf install obs-studio-devel
```

选择适用于本机发行版的命令，开发包与 OBS 运行环境使用相同来源和版本。SDK 需要提供
`libobs` 和 `obs-frontend-api` 两个 CMake 包；下方源码构建步骤会导出这两个包。

#### 从源码生成 SDK

以下命令固定使用 **OBS 31.1.2**，并完成 SDK 的构建与导出。
安装和测试时，请使用相同架构的 OBS 31.1.2 运行环境。
其他 OBS 版本的构建预设、依赖和导出路径可能不同，修改版本前应核对对应标签的源码。

从 **StartLive 仓库根目录**开始执行。各平台步骤将源码克隆到新建的
`build/obs-sdk-src-31.1.2` 目录。每组 OBS 版本、架构和生成器使用独立的构建目录。

这些命令关闭 OBS 的 UI、应用程序前端、内置插件、脚本和浏览器源。
在此版本中，`ENABLE_FRONTEND=OFF` 仍会保留 frontend API 的构建。
编译 `libobs` 和 `obs-frontend-api` 后，安装 `Development` 组件，
即可导出本插件需要的头文件、链接库和 CMake 包。

##### Windows x64

安装 **Visual Studio 2022 Build Tools**、**v143 C++ 工具链**、**ATL**、
**Windows SDK 10.0.22621**、**CMake 3.28+** 和 Git。
已安装 [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/)
的 Windows 机器可在 PowerShell 中执行以下命令，并在安装程序提示时允许提权：

```powershell
winget install --id Git.Git -e --source winget
winget install --id Kitware.CMake -e --source winget
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --source winget --override "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --add Microsoft.VisualStudio.Component.VC.ATL --add Microsoft.VisualStudio.Component.Windows11SDK.22621"
```

安装后重新打开 PowerShell，使 Git 和 CMake 加入 `PATH`，回到 StartLive 仓库根目录，
完整执行下面的命令块。官方预设会将固定版本的依赖包下载到 OBS 源码目录下的
`.deps`，其中包括 obs-deps 和 Qt。配置过程中需要联网。

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

SDK 导出到 `build/obs-sdk-31.1.2-windows-x64`，
其中的 `cmake` 目录包含上面检查的三个包配置文件。

##### macOS arm64 / x86_64

从 [Apple Xcode 下载入口](https://developer.apple.com/xcode/resources/)
安装 **Xcode 16 或更新版本的完整 Xcode，包含 macOS SDK 15 或更新版本**，
并安装 [Homebrew](https://brew.sh/)。
假设 Xcode 位于 `/Applications/Xcode.app`，执行以下初始化操作，
并安装 CMake 3.28+ 和 Git：

```sh
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -runFirstLaunch
xcodebuild -version
xcrun --sdk macosx --show-sdk-platform-version
brew install cmake git
```

在本机架构的终端会话中，回到 StartLive 仓库根目录执行下面的命令。
命令会选择当前机器架构（`arm64` 或 `x86_64`），OBS 运行环境也必须使用相同架构。
官方预设会将固定版本的 obs-deps 和 Qt 依赖包下载到 `.deps`。
部署目标为 macOS 12.0，但构建机器必须能够运行上述版本的 Xcode 和 SDK。
`OBS_CODESIGN_IDENTITY=-` 为本地 SDK 构建使用临时签名（ad hoc）。

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

SDK 导出到 `build/obs-sdk-31.1.2-macos-arm64` 或
`build/obs-sdk-31.1.2-macos-x86_64`。
libobs 以 framework 形式导出，frontend API 以库形式导出，
所以上面显式指定了两者各自的 CMake 包路径。

##### Linux — Ubuntu 24.04 LTS

以下包名和命令适用于 **Ubuntu 24.04 LTS**，会安装 CMake 3.28+、GCC、
Ninja、FFmpeg 6.1 开发文件，以及 libobs、X11、Wayland、OpenGL/EGL 和
PulseAudio 所需的依赖。其他发行版请安装对应开发包，并使用 FFmpeg 6.1 或更新版本。

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

回到 StartLive 仓库根目录执行：

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

SDK 导出到 `build/obs-sdk-31.1.2-linux`，两个 CMake 包都位于 `lib/cmake` 下。
SDK 构建和导出命令使用当前用户权限运行。

##### 使用生成的 SDK

接下来执行下方对应平台的插件编译和安装步骤。
命令默认使用上面生成的 SDK 路径；使用其他位置的 SDK 时，
将 `ObsSdk` / `OBS_SDK` 设为其安装前缀。

开发期间保留 OBS 源码、构建目录和下载的依赖。
`Development` 组件提供编译所需的文件；单独安装 OBS，
为插件加载和捕获测试提供应用程序、运行库和图形模块。

以上版本相关细节以 OBS 31.1.2 的
[构建预设](https://github.com/obsproject/obs-studio/blob/31.1.2/CMakePresets.json)、
[frontend API 配置](https://github.com/obsproject/obs-studio/blob/31.1.2/frontend/CMakeLists.txt)
和 [SDK 导出规则](https://github.com/obsproject/obs-studio/blob/31.1.2/cmake/common/helpers_common.cmake)
为依据。

### StartLive 运行依赖

本地预览和 RTC 验证使用 StartLive 的 Python 环境：

- Python **3.11–3.14**。
- `requirements.txt` 中的应用依赖，包括 PySide6。
- PK 扩展依赖，当前固定为 `aiortc==1.15.0` 和 `aioice==0.10.2`，并自动安装 PyAV
  等传递依赖。

虚拟环境安装命令见下方的启动与验证章节。

## 构建前准备

以下命令均从 **StartLive 仓库根目录**运行，使用完整仓库或包含插件源码的源码发行包。

```text
StartLive/
├── plugins/obs-startlive-pk/
│   ├── CMakeLists.txt
│   └── src/
└── startlive/core/pk/states/encoder.py
```

先运行 `cmake --version`，确认版本满足要求。示例中的 SDK 和 OBS
路径需要按本机安装位置修改。不同平台、架构或生成器使用不同构建目录。
插件构建只生成插件模块，不再包含测试宿主 EXE 或相应构建目标。

## Windows：编译与安装

在 PowerShell 中使用 Visual Studio 2022 和导出的 SDK 配置并编译。
使用其他兼容的 Visual Studio 版本时，选择对应的 CMake 生成器。

```powershell
$ObsSdk = Join-Path $PWD "build/obs-sdk-31.1.2-windows-x64"
$QtSdk = Join-Path $PWD "build/obs-sdk-src-31.1.2/.deps/obs-deps-qt6-2025-07-11-x64"

cmake -S plugins/obs-startlive-pk -B build/obs-pk-windows -G "Visual Studio 17 2022" -A x64 "-DCMAKE_PREFIX_PATH=$ObsSdk;$QtSdk"
if ($LASTEXITCODE -ne 0) { throw "Plugin configure failed" }
cmake --build build/obs-pk-windows --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed" }
```

关闭 OBS，安装到实际使用的 OBS 目录。`ObsRoot` 设为已安装或便携版 OBS 的根目录。
安装到 Program Files 时，使用管理员 PowerShell，并从 StartLive 仓库根目录执行：

```powershell
$ObsRoot = "C:/Program Files/obs-studio"
cmake --install build/obs-pk-windows --config Release --prefix "$ObsRoot"
```

安装位置：`$ObsRoot/obs-plugins/64bit/obs-startlive-pk.dll`。
接下来执行下方的**启动与验证**。

## macOS：编译与安装

完成 Xcode 初始化后，在终端中执行。`PK_ARCH` 使用 OBS 运行环境的架构
（`arm64` 或 `x86_64`），`OBS_SDK` 指向对应架构的 SDK。
以下命令使用上方导出的 SDK，部署目标为 macOS 12.0。

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

关闭 OBS，安装完整插件包：

```sh
cmake --install build/obs-pk-macos --config Release \
  --prefix "$HOME/Library/Application Support/obs-studio/plugins"
```

安装位置：
`~/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin`。
接下来执行下方的**启动与验证**。

## Linux：编译与安装

面向原生安装的 OBS，使用 Ninja 和导出的 SDK 配置并编译：

```sh
set -eu
OBS_SDK="$PWD/build/obs-sdk-31.1.2-linux"

cmake -S plugins/obs-startlive-pk -B build/obs-pk-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$OBS_SDK" \
  -DCMAKE_INSTALL_LIBDIR=lib
cmake --build build/obs-pk-linux --parallel
```

关闭 OBS，将编译产物直接安装到当前用户的 OBS 插件目录：

```sh
PK_PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/obs-studio/plugins/obs-startlive-pk/bin/64bit"
install -Dm755 build/obs-pk-linux/obs-startlive-pk.so \
  "$PK_PLUGIN_DIR/obs-startlive-pk.so"
```

安装位置：
`${XDG_CONFIG_HOME:-$HOME/.config}/obs-studio/plugins/obs-startlive-pk/bin/64bit/obs-startlive-pk.so`。
接下来执行下方的**启动与验证**。
安装布局详见 [OBS 插件指南](https://obsproject.com/kb/plugins-guide)。

## 启动与验证

在仓库根目录安装 StartLive：

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

`python3` 需处于支持的版本范围内；Windows 示例选用 Python 3.11。

1. 安装插件后重启 OBS。
2. 点击 OBS 的 **工具 → StartLive PK 采集：已关闭** 启动采集。成功后显示
   **StartLive PK 采集：已开启**，停止后恢复为 **已关闭**；启动失败仍显示已关闭。
   文字反映实际 OBS 采集状态，不代表 StartLive 客户端是否已连接。
3. 在 StartLive 的“文件”菜单打开 **PK / OBS 媒体窗口**，窗口自动连接并显示 OBS
   节目画面。
4. 将需要发送的音源路由到 OBS 音轨 1，对方回放的声音使用独立监听路径。确认
   StartLive 能收到画面和声音。
5. 关闭 PK 窗口结束预览，再次点击 OBS 工具菜单项停止采集。重新启动采集并打开 PK
   窗口，确认可以恢复连接。OBS 退出时也会停止采集。

OBS 与 StartLive 应使用同一个系统用户运行。每个采集端点仅支持一个媒体客户端。采集开关控制本地媒体连接；线上
PK 的账号、信令和网络流程由 StartLive 处理。

若无法启动采集，检查 OBS 输出尺寸、色彩空间，以及是否有其他 OBS 实例占用端点。
成功启动时，OBS 日志会出现 `[StartLive PK] Capture ... NV12 shared-memory v2`
或 `BGRA shared-memory v2`。若采集已启动但 StartLive 没有画面，检查两端是否均已更新、
是否使用同一个系统用户运行，以及是否已有其他 StartLive 媒体客户端连接。
