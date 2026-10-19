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

需要 Python 3.11–3.14 和桌面环境。记住登录凭据需要可用的系统 keyring 后端。

使用 uv 安装、启动和更新：

```shell
uv tool install startlive
startlive
uv tool upgrade startlive
```

使用 pip：

```shell
python -m pip install startlive
python -m pip install startlive[pk]  # 如果需要使用pk功能
startlive
python -m pip install --upgrade startlive
```

安装后可在任意目录执行 `startlive`；使用 `startlive --help` 查看参数，
使用 `startlive --version` 查看版本。通过该命令启动时使用 uv/pip 更新。
Windows 的配置和日志保存在 `%LOCALAPPDATA%/StartLive` 下，
账号凭据继续使用系统 keyring。

维护者请参阅[PyPI 发布指南](publishing.md)

### Debian / 云桌面的临时登录模式

Linux 未检测到系统密钥环或 keyring 已禁用时，StartLive 会把登录凭据和 OBS 密码保存在
本次进程的内存中，并在状态栏提示临时登录模式。扫码登录、账号切换和 OBS
连接仍可使用；退出后需要重新登录并重新输入 OBS 密码。非敏感偏好设置照常保存。

如需在 Debian 上记住登录，安装 `gnome-keyring` 和 `dbus-user-session`，
在具有 D-Bus 会话且密钥环已解锁的桌面中启动 StartLive。配置完成后重启应用。
已有系统密钥环记录会保留，临时凭据不会写入明文文件。已选用的系统密钥环
之后发生故障时仍会正常报错，避免把暂时无法访问的已保存账号误当成空账号列表。

## 软件截图

![2bf8d9d51186e774903b6cd26831f355](https://github.com/user-attachments/assets/974b0dbb-fcd5-4b26-be76-42db728b8942)

## 使用方法

[点我查看教程（腾讯文档）](https://docs.qq.com/doc/DTHVMdkhtUWJjRFhv?scene=4edcd4a61e4d506148e0f879bN4Lu1)

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Radekyspec/StartLive)

### 前置要求

* `3.11 <= Python <= 3.14`
* `Python 3.14.6` 经测试可用, 推荐使用`3.12.10`
* 桌面端环境
* `PySide6 (Qt for Python)` [支持的架构](https://wiki.qt.io/Qt_for_Python)
* 记住登录凭据需要受 [keyring](https://pypi.org/project/keyring/) 支持的密钥后端存储服务（Linux 下可选）
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
.\venv\Scripts\pip.exe install -e ".[pk]"  # 如果需要使用pk功能
.\venv\Scripts\python.exe .\StartLive.py
```

- **macOS / Linux**:

```shell
./venv/bin/pip install -e .
./venv/bin/pip install -e ".[pk]"  # 如果需要使用pk功能
./venv/bin/python ./StartLive.py
```

> 请注意，Bilibili目前没有对所有用户支持HEVC编码推流，如果推流失败可以检查一下编码。
