<!-- markdownlint-disable -->
<div align="center">

<img alt="LOGO" src="./docs/images/icon_left.png" width="256" height="256" />

# StartLive

Bypass the requirement to use Bilibili’s official "LiveHime" client to start streaming.

Download / Update / Q&A QQ Group: <a href="https://qm.qq.com/q/fPBktdfdrG">1022778201</a>

<a href="./docs/README_zh.md">🇨🇳 简体中文版</a>

</div>
<!-- markdownlint-restore -->

## Disclaimer

- This software is open-sourced under the [GNU General Public License 3.0](https://www.gnu.org/licenses/gpl-3.0.en.html).
- The software **logo is not licensed under GPL-3.0**. All rights are reserved by the artist [花漫酱](https://space.bilibili.com/49468802) and the software developer. You may not claim GPL-3.0 authorization to use the logo without permission, nor use it for any commercial purpose without authorization.

## Install

### Download via Releases

Download link: **[Click here to download](https://github.com/Radekyspec/StartLive/releases/latest)**

### Install via Windows Package Manager (winget)

```shell
winget install Radekyspec.StartLive
```

## Screenshots

![2bf8d9d51186e774903b6cd26831f355](https://github.com/user-attachments/assets/974b0dbb-fcd5-4b26-be76-42db728b8942)

## How to Use

**[Open the step-by-step guide (Tencent Docs)](https://docs.qq.com/doc/DTHVMdkhtUWJjRFhv?scene=4edcd4a61e4d506148e0f879bN4Lu1)**

## Run from Source / Development

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Radekyspec/StartLive)

### Prerequisites

- `3.11 <= Python <= 3.13`
- Tested on **Python 3.13.7**; **Python 3.12.10** recommended
- Desktop environment
- `PySide6 (Qt for Python)` [supported platforms/architectures](https://wiki.qt.io/Qt_for_Python)
- A keyring backend supported by the [`keyring`](https://pypi.org/project/keyring/) package  
  - On **Windows**: typically the built-in [Windows Credential Locker](https://learn.microsoft.com/en-us/windows/apps/develop/security/credential-locker)  
  - On **macOS**: typically the system `Keychain`  

### Install & Run

Create a virtual environment:

```shell
python -m venv venv
```

- **Windows**: 

```shell
.\venv\Script\pip.exe install -r .\requirements.txt
.\venv\Script\python.exe .\StartLive.py
```

- **macOS / Linux**:

```shell
./venv/bin/pip install -r ./requirements.txt
./venv/bin/python ./StartLive.py
```

> Note: Bilibili does **not** enable **HEVC (High Efficiency Video Coding)** streaming for all users. If pushing the stream fails, please check your encoder/codec settings.
