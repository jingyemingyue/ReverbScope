# 开发者版与安装包版

[English](EDITIONS.md) | **简体中文**

RoomScope 只有一套代码，两种默认配置。两者运行同一套分析（`roomscope.core.pipeline.analyze`），读写同样的会话文件，给出同样的数字；区别只在于分析之外的界面显示什么。本文是 [EDITIONS.md](EDITIONS.md) 的简体中文翻译；两者不一致时以英文版为准。

| | 开发者版 | 安装包版（推荐给用户） |
| --- | --- | --- |
| 获取方式 | `git clone` + `pip install -e ".[dev,gui]"`，或 `pip install roomscope-<version>-py3-none-any.whl` | Releases 页面上的 `RoomScope-setup.exe`、`RoomScope-macos-<arch>.dmg`、`roomscope-linux-x86_64.tar.gz` |
| 判断依据 | 不是打包后的程序（未设置 `sys.frozen`） | PyInstaller 打包程序 |
| 帮助 ▸ 用于问题报告的环境报告（可探测采样率） | 有 | 有 |
| 开发者菜单（音频设备检查器、打开数据文件夹） | 有 | 无，除非手动开启 |
| 独立模式中的高级音频选项（延迟、WASAPI 独占、Core Audio 设置采样率） | 有 | 无，除非手动开启 |
| 日常设置（语言、主题、默认录音配置、音频后端、输出文件夹） | 有 | 有 |
| 扩展 RoomScope | Python API、`roomscope.exporters` 入口点、测试、`scripts/build_release.py` | — |

可用 `ROOMSCOPE_EDITION=developer` 或 `ROOMSCOPE_EDITION=user` 临时覆盖；已安装的 RoomScope 可在“设置 ▸ *显示开发者工具*”中永久开启开发者工具（重启后生效）。命令行工具在两个版本中相同：`roomscope devices --probe`、`roomscope doctor` 以及 `measure` 的 `--latency`、`--wasapi-exclusive`、`--coreaudio-set-rate` 选项始终可用。

## 开发者版的用途

* **调试设备链路。** 开发者 ▸ *音频设备检查器* 列出所有主机 API 和设备，探测每个设备在单声道下接受的采样率（不会播放任何声音），并可把设备清单复制为 JSON 以便提交问题。各主机 API 对信号的影响及其出处见 [AUDIO_DEVICES.zh-CN.md](AUDIO_DEVICES.zh-CN.md)。
* **问题报告**（两个版本都有）。帮助 ▸ *用于问题报告的环境报告*（或 `roomscope doctor`，加 `--probe` 探测采样率）显示版本和构建提交、NumPy、SciPy、libsndfile、PortAudio 和 Qt 的版本、设置、RoomScope 使用的路径（主目录显示为 `~`）以及它看到的音频设备。不会发送任何内容，由用户自行复制到 issue 中。
* **扩展。** 导出器通过 `roomscope.exporters` 入口点注册（见 `roomscope.io.exporters`）；分析本身是普通的 Python API（README ▸ Python API）。贡献方式见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
* **构建发布包。** `scripts/build_release.py` 在本机构建当前平台的安装包版（[RELEASE_PLAN.zh-CN.md](RELEASE_PLAN.zh-CN.md) §3a）。

## 安装包版保持简单

安装包版打开后是包含三种工作流程的主页，设置对话框只保留用户会改的内容：语言、主题（跟随系统、浅色、深色）、默认录音配置、音频后端、默认输出文件夹，以及是否把原始录音复制进每个会话。独立模式仍会按主机 API 列出设备、预选本平台推荐的主机 API、用星标标出推荐的输入和输出，并在播放前检查主机 API、声道和是否使用了两个独立时钟。
