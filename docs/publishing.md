# 发布到 PyPI

项目使用 `pyproject.toml` 和 setuptools 构建，发行名及安装后的命令均为
`startlive`。版本唯一来源是 `src/core/constant/_version.py`，
依赖来源是 `requirements.txt`，无需另加 `setup.py`。

## 本地构建和验证

在项目根目录执行（需要 Python 3.11–3.14）：

```shell
python -m pip install --upgrade build twine
python -m build
python -m twine check --strict dist/*
python tools/check_distribution.py dist/startlive-1.2.1-py3-none-any.whl
```

替换文件名中的版本号。也可以使用 `uv build` 构建。
默认构建先生成 sdist，再从 sdist 构建 wheel，确保源码包可独立构建。
检查脚本会检查资源和命令入口，并在临时虚拟环境中、源码目录之外
验证 `startlive --help` 和 `startlive --version`。它不安装运行依赖，
因此还需在桌面环境中验证真实启动：

```shell
uv tool install --force ./dist/startlive-1.2.1-py3-none-any.whl
startlive
```

本地 wheel 安装用于测试；正式发布后，应重新安装索引中的包，
后续更新才跟随 PyPI：

```shell
uv tool uninstall startlive
uv tool install startlive
uv tool upgrade startlive
```

正式上传前清理自己之前生成的旧版 dist 产物，避免误上传。
wheel 只包含应用代码、图标、版本资源和许可证；不包含本地配置、
日志、虚拟环境和字节码。现有源码和独立安装包的构建入口仍为
`StartLive.py`。

## 首次配置 Trusted Publishing

1. 登录 PyPI，确认你拥有 `startlive` 项目名。若尚未创建项目，可配置
   pending publisher；如果名称已被其他人占用，需先解决名称归属，
   不能直接覆盖，也无法用其他发行名实现 `uv tool upgrade startlive`。
2. 在 PyPI 的 publishing 设置中添加 GitHub publisher：
    - Project name: `startlive`
    - Owner: 发布所用 GitHub 仓库的所有者（上游为 `Radekyspec`）
    - Repository: `StartLive`
    - Workflow filename: `publish-pypi.yml`
    - Environment: `pypi`
3. 在 GitHub 仓库中创建 `pypi` environment。建议设置发布审批人，
   并将允许发布的分支或标签限制到正式发布来源。
4. 修改版本文件并提交，创建同版本的 GitHub Release，例如版本
   `1.2.1` 对应 tag `1.2.1`，Release 标题也可以填写 `1.2.1`。
   tag 兼容可选的 `v` 前缀，因此 `v1.2.1` 同样有效。
   工作流读取 `github.event.release.tag_name`，去掉可选的 `v` 前缀后，
   必须与包版本完全一致；Release 标题不参与 PyPI 版本校验。
   包版本来自该 tag 所指提交中的 `src/core/constant/_version.py`，
   不会根据 tag 或标题自动修改。

工作流在 PR、master 推送时只构建、检查；
发布 GitHub Release 或手动触发工作流时上传 PyPI。构建后在 Windows、macOS、Linux
分别验证命令安装，全部通过才发布。身份验证使用短期 OIDC 凭据，
无需保存 PyPI API token。这里的检查不替代各平台的完整桌面功能测试。

每个已发布的 PyPI 版本不可覆盖；修复后需要递增版本号。
仓库中添加工作流不会自动创建 PyPI 账号、项目或 publisher。

## 在 GitHub Actions 中手动发布

1. 将工作流提交到仓库默认分支，以显示手动运行入口。
2. 在要发布的分支中更新 `src/core/constant/_version.py` 并提交，
   确保版本号尚未发布到 PyPI，且该分支包含支持手动发布的工作流。
3. 打开 **Actions → Build and publish Python package → Run workflow**，
   选择要发布的分支，然后点击 **Run workflow**。
4. 构建和三个平台的安装检查通过后，`publish` 任务会上传 PyPI。
   如果 `pypi` environment 配置了审批或分支限制，仍需满足这些条件。

手动发布不要求创建 Release；包版本直接取所选分支中的版本文件，
不会执行 Release tag 校验。手动运行会实际发布，不再只是构建检查。

## 手动上传

如不使用 GitHub Trusted Publishing，可以用自己配置的凭据上传：

```shell
python -m twine upload --repository testpypi dist/*
python -m twine upload dist/*
```

先检查上传目标及产物。TestPyPI 和 PyPI 使用独立账号配置及凭据。
本次文件准备不会执行上传。

## 安装后的行为

- `startlive` 在任意工作目录启动，资源从安装位置读取。
- 通过该入口启动时，禁用 Velopack 自更新，使用 uv 或 pip 更新。
- Windows 配置和日志分别位于 `%LOCALAPPDATA%/StartLive/config`、
  `%LOCALAPPDATA%/StartLive/logs`，升级不会删除它们。
- Linux 延续 `~/.cache/StartLive/`，macOS 延续
  `~/Library/Application Support/StartLive` 和 `~/Library/Logs/StartLive`。
- 账号凭据继续使用系统 keyring；从源码运行迁移到包安装时，
  如需保留旧目录的其他本地配置，请手动复制到上述目录。
- 仍然需要桌面环境及可用的系统 keyring 后端。

参考：[setuptools 配置](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)、
[uv 工具安装与升级](https://docs.astral.sh/uv/guides/tools/)、
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。
