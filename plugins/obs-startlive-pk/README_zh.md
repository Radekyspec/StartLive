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

发布构建固定使用 **OBS 28.0.0**、**Qt 6.3.1** 和官方
**obs-deps 2022-08-02** 依赖包，依据是
[OBS 28 官方工作流](https://github.com/obsproject/obs-studio/blob/28.0.0/.github/workflows/main.yml)
及[对应依赖发布页](https://github.com/obsproject/obs-deps/releases/tag/2022-08-02)。
下载后校验 SHA256，再解压使用。

目标是兼容相同架构的 **OBS 28 及以上版本**。使用较低版本的公开 OBS/Qt API，
可避免引用新版才提供的符号，但不能保证所有未来版本都兼容。
每个支持版本仍需验证加载、菜单文字更新、音视频采集和断线重连；OBS 27 / Qt 5 不在范围内。

| 平台                  | 固定 CI runner / 编译工具                                                                 | 插件运行下限                              |
|---------------------|-------------------------------------------------------------------------------------|-------------------------------------|
| Windows x64         | `windows-2025-vs2026`、VS 2026 生成器、**v142 14.29.30133**、Windows SDK **10.0.26100.0** | Windows 10、OBS 28+ x64、兼容的 VC++ 运行库 |
| macOS Intel         | `macos-15-intel`、**Xcode 16.4**、macOS SDK **15.5**                                  | macOS **10.15**、OBS 28+ x86_64      |
| macOS Apple Silicon | `macos-15`、**Xcode 16.4**、macOS SDK **15.5**                                        | macOS **11.0**、OBS 28+ arm64        |

CMake 固定为 **4.2.3**。这些 runner 已预装对应 MSVC 工具集、Windows SDK 或 Xcode，
CI 无需再安装另一套 VS / Xcode。最新 MSVC 已移除 Qt 6.3.1 使用的 `stdext` 接口，
因此插件明确选择 v142；Nuitka 仍使用 runner 的当前 MSVC。
这里的系统下限只针对插件，开播器本身还受 Python/PySide 等依赖的要求限制。
Windows API 目标设为 Windows 10；Qt 6.3 官方测试的 Windows 10 配置为 21H2 及以上，
不据此承诺所有更早的 Windows 10 系统构建均受支持。

从 StartLive 仓库根目录开始，使用全新的构建目录：

```sh
python -m pip install cmake==4.2.3
git clone --branch 28.0.0 --depth 1 https://github.com/obsproject/obs-studio.git build/obs-sdk-source
```

#### Windows SDK

本机构建需安装 VS 2026 的 v142 x64 工具集和 Windows SDK 10.0.26100.0。
`VsRoot` 改为实际安装目录；示例与 CI 的 Enterprise 路径一致。

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

安装完整 Xcode 16.4。以下示例选择 Apple Silicon；Intel 请按注释同时修改
依赖架构、`PK_ARCH` 和部署目标。OBS 28 的 SDK 安装组件名为 `obs_libraries`，
其 macOS 导出会漏掉公开 frontend 头文件，因此最后一行从固定版本源码补齐该文件。

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

SDK 位于 `build/obs-sdk`，Qt 及原生构建依赖位于 `build/obs-pk-deps`。
重新编译的 OBS 库和这套 Qt 运行库都不会随插件分发，插件运行时使用宿主 OBS 的库。
完整 CI 步骤见[共享构建动作](../../.github/actions/build-obs-pk/action.yml)。

macOS 参数说明：

- `CMAKE_OSX_DEPLOYMENT_TARGET` 决定插件最低系统版本，Intel 为 10.15，ARM64 为
  11.0。
- `CMAKE_OSX_SYSROOT=macosx15.5` 选择编译用 SDK，不等于要求用户系统为 15.5。
- `CODE_SIGNING_ALLOWED=NO` 和 `OBS_CODESIGN_LINKER=OFF` 关闭中间构建的签名；
  Nuitka 打包后仍对插件和 `.app` 执行 ad hoc 签名。正式分发时仍需按发布流程处理签名、公证。
- `BUNDLE=TRUE`、`.plugin` 扩展名、`LIBRARY DESTINATION .` 保证 OBS 可识别的目录布局；
  `MODULE` 插件安装时必须使用 `LIBRARY`，不能用只适用于应用程序的 `BUNDLE` 安装类别。
- `INSTALL_RPATH=@executable_path/../Frameworks` 让插件找到 OBS 自带的库。
- 去掉 Qt 添加的 `AGL` 链接不影响旧版 64 位 macOS；AGL 在 64 位上无实际功能。
  改用 `OpenGL::GL` 保留 OpenGL 链接，并修正 Qt 6.3.1 对新版 CMake framework
  路径的误读。
- 旧的 `OBS_CODESIGN_IDENTITY`、`ENABLE_FRONTEND` 和 `--preset` 不适用于此 OBS 28
  构建流程，
  已改为它实际支持的参数；关闭 OBS UI 仍会构建 frontend API，不会关闭插件的 OBS
  菜单功能。

#### Linux SDK

Linux 不在发布 CI 矩阵中。本机构建请安装与原生 OBS 28+ 匹配的 OBS 开发包和 Qt 6
开发文件，
例如 Debian/Ubuntu 的 `libobs-dev`、`qt6-base-dev`，或 Fedora 的
`obs-studio-devel`、`qt6-qtbase-devel`。SDK 必须提供 `libobs`、`obs-frontend-api`
两个 CMake 包。发行版构建受当地依赖版本约束，不自动获得 Windows/macOS 的二进制兼容范围。

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

在 PowerShell 中使用 Visual Studio 2026 + v142 和导出的 SDK 配置并编译。
复用上方 Windows SDK 步骤中已设置的 `VsArgs`。

```powershell
$ObsSdk = Join-Path $PWD "build/obs-sdk"
$QtSdk = Join-Path $PWD "build/obs-pk-deps"

python -m cmake -S plugins/obs-startlive-pk -B build/obs-pk-windows @VsArgs "-DCMAKE_PREFIX_PATH=$ObsSdk;$QtSdk"
if ($LASTEXITCODE -ne 0) { throw "Plugin configure failed" }
python -m cmake --build build/obs-pk-windows --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed" }
```

关闭 OBS，安装到实际使用的 OBS 目录。`ObsRoot` 设为已安装或便携版 OBS 的根目录。
安装到 Program Files 时，使用管理员 PowerShell，并从 StartLive 仓库根目录执行：

```powershell
$ObsRoot = "C:/Program Files/obs-studio"
python -m cmake --install build/obs-pk-windows --config Release --prefix "$ObsRoot"
```

安装位置：`$ObsRoot/obs-plugins/64bit/obs-startlive-pk.dll`。
接下来执行下方的**启动与验证**。

## macOS：编译与安装

完成 Xcode 初始化后，在终端中执行。`PK_ARCH` 使用 OBS 运行环境的架构
（`arm64` 或 `x86_64`），`OBS_SDK` 指向对应架构的 SDK。
以下命令选择 ARM64 / macOS 11.0；Intel 请改为 x86_64 / 10.15。

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

关闭 OBS，安装完整插件包：

```sh
python -m cmake --install build/obs-pk-macos --config Release \
  --prefix "$HOME/Library/Application Support/obs-studio/plugins"
codesign --force --sign - --timestamp=none \
  "$HOME/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin"
```

安装位置：
`~/Library/Application Support/obs-studio/plugins/obs-startlive-pk.plugin`。
接下来执行下方的**启动与验证**。

## Linux：编译与安装

面向原生安装的 OBS，使用 Ninja 和发行版提供的 OBS/Qt 开发包配置并编译：

```sh
set -eu

cmake -S plugins/obs-startlive-pk -B build/obs-pk-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
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
