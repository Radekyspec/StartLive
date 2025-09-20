<!-- markdownlint-disable -->
<div align="center">

<img alt="LOGO" src="./docs/images/icon_left.png" width="256" height="256" />

# StartLive

绕过强制使用直播姬开播的要求

下载/更新/答疑QQ群：[1022778201](https://qm.qq.com/q/fPBktdfdrG)

</div>
<!-- markdownlint-restore -->

## 声明
- 本软件使用 [GNU General Public License 3.0](https://www.gnu.org/licenses/gpl-3.0.zh-cn.html) 协议开源
- 本软件 logo 并非使用 GPL-3.0 协议开源，画师[花漫酱](https://space.bilibili.com/49468802)及软件开发者保留所有权利。不得以 GPL-3.0 协议已授权为由在未经授权的情况下使用本软件 logo，不得在未经授权的情况下将本软件 logo 用于任何商业用途。

## 安装

### 通过 Releases 下载

下载链接：[点击这里下载](https://github.com/Radekyspec/StartLive/releases/latest)

### 通过 Windows Package Manager (winget) 下载

```shell
winget install Radekyspec.StartLive
```

## 软件截图

![2bf8d9d51186e774903b6cd26831f355](https://github.com/user-attachments/assets/974b0dbb-fcd5-4b26-be76-42db728b8942)

## 使用方法

[点我查看教程（腾讯文档）](https://docs.qq.com/doc/DTHVMdkhtUWJjRFhv?scene=4edcd4a61e4d506148e0f879bN4Lu1)

## 从源代码运行/开发

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Radekyspec/StartLive)

### 前置要求

* `3.10 <= Python <= 3.13`
* `Python 3.13.7` 经测试可用, 推荐使用`3.12.10`
* 桌面端环境
* `PySide6 (Qt for Python)` [支持的架构](https://wiki.qt.io/Qt_for_Python)
* 受 [keyring](https://pypi.org/project/keyring/) 支持的密钥后端存储服务
  - 在 `Windows` 上通常为系统自带的 [Windows Credential Locker](https://learn.microsoft.com/en-us/windows/apps/develop/security/credential-locker)
  - 在 `macOS` 上通常为系统自带的 [Keychain钥匙串](https://en.wikipedia.org/wiki/Keychain_%28software%29)

### 安装依赖

* 创建虚拟环境

```shell
python -m venv venv
```

* `Windows`: 可以直接双击运行 `install-requirements.bat`

* `MacOS` / `Linux`:

```shell
./venv/bin/pip install -r ./requirements.txt
./venv/bin/pip install git+https://github.com/Radekyspec/PyQtDarkTheme.git@main
```

### 运行app

```shell
python StartLive.py
```

> 请注意，Bilibili目前没有对所有用户支持HEVC编码推流，如果推流失败可以检查一下编码。
