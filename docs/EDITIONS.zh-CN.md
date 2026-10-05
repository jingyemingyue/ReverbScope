# 版本：桌面版、终端版与开发者工具

[English](EDITIONS.md) | **简体中文**

ReverbScope 只有一套代码。它提供两个可下载的**版本**，而且任何一份都可以显示或隐藏**开发者工具**。所有形式运行同一套分析（`reverbscope.core.pipeline.analyze`），读写同样的会话文件，给出同样的数字。本文是 [EDITIONS.md](EDITIONS.md) 的简体中文翻译；两者不一致时以英文版为准。

## 桌面版与终端版

| | 桌面版（Desktop Edition） | 终端版（Terminal Edition） |
| --- | --- | --- |
| 下载文件 | `ReverbScope-Desktop-macOS-arm64.dmg`、`ReverbScope-Desktop-macOS-x86_64.dmg`、`ReverbScope-Desktop-Windows-x64-Setup.exe`、`ReverbScope-Desktop-Windows-x64.zip`、`ReverbScope-Desktop-Linux-x86_64.tar.gz` | `ReverbScope-Terminal-macOS-arm64.tar.gz`、`ReverbScope-Terminal-macOS-x86_64.tar.gz`、`ReverbScope-Terminal-Windows-x64.zip`、`ReverbScope-Terminal-Linux-x86_64.tar.gz` |
| 图形界面（窗口、图表） | 有 | 没有：`reverbscope gui` 会提示安装桌面版 |
| 命令行（`reverbscope`，全部命令） | 有 | 有 |
| 分析、对比、独立模式测量、中英文 | 有 | 有 |
| 包含的内容 | Python 运行时、NumPy、SciPy、soundfile、sounddevice、matplotlib、PySide6 Essentials（Qt） | Python 运行时、NumPy、SciPy、soundfile、sounddevice；不含 Qt、PySide6 和 matplotlib |
| 需要 Python | 不需要 | 不需要 |
| 适合 | 大多数用户 | 命令行、自动化、服务器和没有图形桌面的电脑 |

两个版本由发布工作流的同一个任务、用同一个 PyInstaller spec 构建（`packaging/reverbscope.spec`，`REVERBSCOPE_PACKAGE=desktop|terminal`）。终端版不包含 `reverbscope.ui`、PySide6、shiboken6 和 matplotlib；只要残留其中任何文件，`scripts/check_bundle_contents.py --terminal` 就会让构建失败；`scripts/smoke_bundle.py --terminal` 会用中英文运行演示，检查 `--format json` 只输出 JSON，并确认 `reverbscope gui` 给出一句说明而不是回溯信息。`build_info.json` 记录了版本（`"package"`），`reverbscope doctor` 会显示它。在 Linux x86_64 上，终端版压缩后约 60 MB，桌面版约 150 MB。

## 开发者工具

开发者工具是另一项独立的选择：同一个程序的两种默认配置。

| | 开发者默认配置 | 安装后的默认配置（推荐给用户） |
| --- | --- | --- |
| 获取方式 | `git clone` + `pip install -e ".[dev,gui]"`，或 `pip install reverbscope-<version>-py3-none-any.whl` | Releases 页面上的任一版本 |
| 判断依据 | 不是打包后的程序（未设置 `sys.frozen`） | PyInstaller 打包程序 |
| 帮助 ▸ 用于问题报告的环境报告（可探测采样率） | 有 | 有 |
| 开发者菜单（音频设备检查器、打开数据文件夹） | 有 | 无，除非手动开启 |
| 独立模式中的高级音频选项（延迟、WASAPI 独占、Core Audio 设置采样率） | 有 | 无，除非手动开启 |
| 日常设置（语言、主题、默认录音配置、音频后端、输出文件夹） | 有 | 有 |
| 扩展 ReverbScope | Python API、`reverbscope.exporters` 入口点、测试、`scripts/build_release.py` | — |

可用 `REVERBSCOPE_EDITION=developer` 或 `REVERBSCOPE_EDITION=user` 临时覆盖；已安装的 ReverbScope 可在“设置 ▸ *显示开发者工具*”中永久开启开发者工具（重启后生效）。命令行工具在两个版本中相同：`reverbscope devices --probe`、`reverbscope doctor` 以及 `measure` 的 `--latency`、`--wasapi-exclusive`、`--coreaudio-set-rate` 选项始终可用。

### 开发者默认配置的用途

* **调试设备链路。** 开发者 ▸ *音频设备检查器* 列出所有主机 API 和设备，探测每个设备在单声道下接受的采样率（不会播放任何声音），并可把设备清单复制为 JSON 以便提交问题。各主机 API 对信号的影响及其出处见 [AUDIO_DEVICES.zh-CN.md](AUDIO_DEVICES.zh-CN.md)。
* **问题报告**（两个版本都有）。帮助 ▸ *用于问题报告的环境报告*（或 `reverbscope doctor`，加 `--probe` 探测采样率）显示版本和构建提交、NumPy、SciPy、libsndfile、PortAudio 和 Qt 的版本、设置、ReverbScope 使用的路径（主目录显示为 `~`）以及它看到的音频设备。不会发送任何内容，由用户自行复制到 issue 中。
* **扩展。** 导出器通过 `reverbscope.exporters` 入口点注册（见 `reverbscope.io.exporters`）；分析本身是普通的 Python API（README ▸ Python API）。贡献方式见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
* **构建发布包。** `scripts/build_release.py` 在本机构建当前平台的两个版本（[RELEASE_PLAN.zh-CN.md](RELEASE_PLAN.zh-CN.md) §3a）。

### 安装后的默认配置保持简单

安装好的桌面版打开后是包含三种工作流程的主页，设置对话框只保留用户会改的内容：语言、主题（跟随系统、浅色、深色）、默认录音配置、音频后端、默认输出文件夹，以及是否把原始录音复制进每个会话。独立模式仍会按主机 API 列出设备、预选本平台推荐的主机 API、用星标标出推荐的输入和输出，并在播放前检查主机 API、声道和是否使用了两个独立时钟。
