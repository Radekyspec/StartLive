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

### Install via AUR (Arch Linux/Manjaro)

> Install `startlive-git` using an AUR helper (e.g. `paru`, `yay`, `pikaur`).

```shell
paru -S startlive-git
```

Supported Linux installations are managed and updated through the system
package manager. The in-app Velopack updater is disabled on Linux, so Velopack
does not need to be installed separately.

## Screenshots

![2bf8d9d51186e774903b6cd26831f355](https://github.com/user-attachments/assets/974b0dbb-fcd5-4b26-be76-42db728b8942)

## How to Use

**[Open the step-by-step guide (Tencent Docs)](https://docs.qq.com/doc/DTHVMdkhtUWJjRFhv?scene=4edcd4a61e4d506148e0f879bN4Lu1)**

## Run from Source / Development

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Radekyspec/StartLive)

### Prerequisites

- `3.12 <= Python < 3.15` (the repository defaults to Python 3.14)
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Desktop environment
- `PySide6 (Qt for Python)` [supported platforms/architectures](https://wiki.qt.io/Qt_for_Python)
- A keyring backend supported by the [`keyring`](https://pypi.org/project/keyring/) package
  - On **Windows**: typically the built-in [Windows Credential Locker](https://learn.microsoft.com/en-us/windows/apps/develop/security/credential-locker)
  - On **macOS**: typically the system `Keychain`
  - On **Linux**: install and unlock a Secret Service provider such as GNOME Keyring or KWallet; use `uv run keyring diagnose` to inspect the selected backend

### Install & Run

`uv` creates `.venv` and installs the dependency versions recorded in `uv.lock`:

```shell
git clone https://github.com/Radekyspec/StartLive.git
cd StartLive
uv sync --locked
uv run python StartLive.py
```

Run Ruff before contributing:

```shell
uv run ruff check .
```

> Note: Bilibili does **not** enable **HEVC (High Efficiency Video Coding)** streaming for all users. If pushing the stream fails, please check your encoder/codec settings.
