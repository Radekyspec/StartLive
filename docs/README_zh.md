<!-- markdownlint-disable -->
<div align="center">

<img alt="LOGO" src="./images/icon_left.png" width="256" height="256" />

# StartLive

绕过强制使用直播姬开播的要求

下载/更新/答疑QQ群：[1022778201](https://qm.qq.com/q/fPBktdfdrG)

</div>
<!-- markdownlint-restore -->

## 声明
- 本软件使用 [GNU General Public License 3.0](https://www.gnu.org/licenses/gpl-3.0.zh-cn.html) 协议开源
- 本软件 logo 并非使用 GPL-3.0 协议开源，画师[花漫酱](https://space.bilibili.com/49468802)及软件开发者保留所有权利。不得以 GPL-3.0 协议已授权为由在未经授权的情况下使用本软件 logo，不得在未经授权的情况下将本软件 logo 用于任何商业用途。

### 通过 Releases 下载

下载链接：[点击这里下载](https://github.com/Radekyspec/StartLive/releases/latest)

### 通过 Windows Package Manager (winget) 下载

```shell
winget install Radekyspec.StartLive
```

### 通过 AUR (Arch Linux/Manjaro) 安装

> 需要使用一个 AUR helper，比如 `paru`、`yay`、`pikaur` 等

```shell
paru -S startlive-git
```

受支持的 Linux 安装由系统包管理器负责安装和更新。Linux 下会禁用应用内的
Velopack 更新器，因此无需单独安装 Velopack。

### 从 PyPI 安装

需要 Python 3.11–3.14、桌面环境以及可用的系统 keyring 后端。

使用 uv 安装、启动和更新：

```shell
uv tool install startlive
startlive
uv tool upgrade startlive
```

使用 pip：

```shell
python -m pip install startlive
startlive
python -m pip install --upgrade startlive
```

安装后可在任意目录执行 `startlive`；使用 `startlive --help` 查看参数，
使用 `startlive --version` 查看版本。通过该命令启动时使用 uv/pip 更新。
Windows 的配置和日志保存在 `%LOCALAPPDATA%/StartLive` 下，
账号凭据继续使用系统 keyring。

维护者请参阅[PyPI 发布指南](publishing.md)

## 软件截图

![2bf8d9d51186e774903b6cd26831f355](https://github.com/user-attachments/assets/974b0dbb-fcd5-4b26-be76-42db728b8942)

## 使用方法

[点我查看教程（腾讯文档）](https://docs.qq.com/doc/DTHVMdkhtUWJjRFhv?scene=4edcd4a61e4d506148e0f879bN4Lu1)

## 直播姬配置转换

在菜单栏选择 **特殊功能 → 配置转换**，选择直播姬配置，点击“分析并预览”，检查转换提示后导出
JSON。
然后在 OBS 中选择 **场景集合 → 导入**，选择导出的文件。

可勾选“过滤以 Vertical、wDouble、xDouble 开头的场景”。此选项默认关闭，按名称开头区分大小写匹配，
仅移除场景及其列表项、引用，保留图片、音频等素材和分组。当前场景被过滤时切换到第一个保留场景；
如果全部场景都被过滤，则提示取消过滤。切换选项后需重新分析预览才能导出。

直播姬的场景数据与安装目录分开保存。Windows 默认配置目录是
`%LOCALAPPDATA%\bililive\User Data\<B站UID>\`：

| 文件                                               | 内容                                 |
|--------------------------------------------------|------------------------------------|
| `Scene Collection\support_group_collection.json` | 支持分组的场景配置；在本机直播姬 8.7 中找到，自动查找时优先列出 |
| `untitledv2.json` / `untitled.json`              | 其他或旧版场景配置，内容可能与分组版本不同              |
| `Preferences`                                    | 应用、视频等偏好设置，不是场景文件                  |

支持自动查找多个账号，也可选择账号目录、`Scene Collection` 目录、JSON 文件或
`.json.bak` 备份。
建议退出直播姬后再读取，以获得已保存的最新配置。

- 保留 OBS 支持的场景、分组、嵌套场景、图层顺序、位置、缩放、裁剪、旋转、可见性，以及音频和转场。
- 桌面音频和麦克风字段转换为 OBS 全局音频设备字段；仅保留 OBS 的六条音轨。
- 直播姬专用源、滤镜和转场按兼容名单跳过，同时移除对已跳过素材的引用；转换预览中列出具体项目。
- 不同尺寸的嵌套场景会保留，但横竖屏同时输出、双屏模式、美颜、连麦等直播姬专属功能不迁移。
- 参考画布从场景坐标推断；不能确定时可填写原始宽高。导入后需核对 OBS
  基础画布、音频/摄像头设备和素材路径。
- 素材文件不打包。导出使用新文件名，不覆盖直播姬或 OBS 原配置；不迁移账号、推流地址或编码器配置。

转换规则依据本机配置与 OBS 官方的
[场景集合加载代码](https://github.com/obsproject/obs-studio/blob/master/frontend/widgets/OBSBasic_SceneCollections.cpp)、
[场景项目序列化代码](https://github.com/obsproject/obs-studio/blob/master/libobs/obs-scene.c)
核对。
未引入第三方转换依赖。

## 从源代码运行/开发

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Radekyspec/StartLive)

### 前置要求

* `3.11 <= Python <= 3.14`
* `Python 3.14.6` 经测试可用, 推荐使用`3.12.10`
* 桌面端环境
* `PySide6 (Qt for Python)` [支持的架构](https://wiki.qt.io/Qt_for_Python)
* 受 [keyring](https://pypi.org/project/keyring/) 支持的密钥后端存储服务
  - 在 `Windows` 上通常为系统自带的 [Windows Credential Locker](https://learn.microsoft.com/en-us/windows/apps/develop/security/credential-locker)
  - 在 `macOS` 上通常为系统自带的 [Keychain钥匙串](https://en.wikipedia.org/wiki/Keychain_%28software%29)

### 安装 & 运行

* 创建虚拟环境

```shell
python -m venv venv
```

- **Windows**: 

```shell
.\venv\Scripts\pip.exe install -e .
.\venv\Scripts\python.exe .\StartLive.py
```

- **macOS / Linux**:

```shell
./venv/bin/pip install -e .
./venv/bin/python ./StartLive.py
```

> 请注意，Bilibili目前没有对所有用户支持HEVC编码推流，如果推流失败可以检查一下编码。
