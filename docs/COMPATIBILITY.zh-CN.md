# 兼容性

[English](COMPATIBILITY.md) | **简体中文**

ReverbScope 能在哪些平台上运行、能与哪些东西配合，以及**每一行是用什么方式验证的**。写着“未验证”的行是一个还没有人检查过的说法。本文是 [COMPATIBILITY.md](COMPATIBILITY.md) 的简体中文翻译；两者不一致时以英文版为准。最后审查：2026-09-29。

## 操作系统与安装包

| 平台 | 交付物 | 验证方式 |
| --- | --- | --- |
| Windows 10/11 x64 | 桌面版：`ReverbScope-Desktop-Windows-x64-Setup.exe`、`ReverbScope-Desktop-Windows-x64.zip`；终端版：`ReverbScope-Terminal-Windows-x64.zip` | `windows-latest` 上的发布工作流：冻结包冒烟测试（命令行、中英文演示、stdout 只有 JSON、模拟测量、离屏图形界面、不带参数启动的窗口启动器），用 Inno Setup 构建安装程序，按当前用户安装、检查开始菜单项，在安装目录中冒烟测试，再卸载并确认开始菜单项已删除；终端版经过“不含 Qt / PySide6 / matplotlib”门禁和冒烟测试（演示、JSON、`gui` 友好拒绝）；Windows / Python 3.12 上的 CI 测试套件 |
| macOS 14+，Apple 芯片 | 桌面版：`ReverbScope-Desktop-macOS-arm64.dmg`；终端版：`ReverbScope-Terminal-macOS-arm64.tar.gz` | `macos-latest`（macOS 26）上的发布工作流：挂载 DMG、复制应用、`gui --smoke`、模拟 Finder 方式启动并保持运行、验证临时签名（ad hoc）、`lipo` 架构为 arm64、启动一份启用 hardened runtime 的副本；两个版本的 `reverbscope doctor` 都报告 `arm64`；终端版经过不含 Qt 的门禁和冒烟测试；macOS / Python 3.12 上的 CI 测试套件。macOS 14 是打包的 NumPy / SciPy wheel 的最低版本（`macosx_14_0`，`LSMinimumSystemVersion` 14.0），尚未在 macOS 14 上实际运行过 |
| macOS 14+，Intel | 桌面版：`ReverbScope-Desktop-macOS-x86_64.dmg`；终端版：`ReverbScope-Terminal-macOS-x86_64.tar.gz` | `macos-15-intel`（macOS 15）上的发布工作流：同样的检查，架构为 x86_64 |
| Linux x86_64（CI 运行器的 glibc 或更新版本） | 桌面版：`ReverbScope-Desktop-Linux-x86_64.tar.gz`；终端版：`ReverbScope-Terminal-Linux-x86_64.tar.gz` | `ubuntu-latest` 上的发布工作流及本地构建（`scripts/build_release.py`）：两个版本的安装包门禁和冒烟测试、启动 `reverbscope-gui`；Ubuntu / Python 3.12–3.14 上的 CI 测试 |
| 其他（ARM 版 Windows / Linux、更旧的 macOS） | 仅 wheel | 未验证；`scripts/build_release.py` 拒绝把 ARM 构建命名为 x86_64 |

还没有任何安装包在个人自己的电脑上配合真实音频硬件使用过（[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)）；上表各行都是 CI 和本地构建的结果。

## Python 与依赖

| | 最低声明版本 | 已检查的最新版本 |
| --- | --- | --- |
| Python | 3.12 | 3.14 |
| NumPy | 1.26 | 2.5.3 |
| SciPy | 1.12 | 1.18.1 |
| soundfile / libsndfile | 0.12 | 0.14.0 / 1.2.2 |
| sounddevice / PortAudio | 0.4.6 | 0.5.6 / V19.7（Windows、macOS 上随包提供）；Linux 使用系统的 `libportaudio2`（Ubuntu 24.04 上为 V19.6） |
| matplotlib | **3.10** | 3.11.2 |
| PySide6_Essentials | 6.6 | 6.11.2 |

2026-09-24 验证：在 Python 3.12 上安装恰好为声明下限的版本，在 Python 3.13 和 3.14 上安装最新版本，并运行完整测试套件。除 matplotlib 3.8 / 3.9 外，下限版本全部通过；这两个版本的 wheel 仍包含 `_ttconv` 扩展（[DEPENDENCIES.md](DEPENDENCIES.md) §6），因此下限提高到 3.10，之后通过。在 3.13 和 3.14 上无法安装声明的下限版本（没有对应的 wheel），解析器会选择更新的版本（例如 3.13 上的 PySide6_Essentials 6.8.0.2）；只测试了 Python 3.12 上的下限组合。桌面安装包固定使用 `requirements/bundle.lock` 中的版本。

## 录音文件（通用 DAW 模式）

同一段录音以每种封装格式测试（`tests/integration/test_daw_exports.py`）：WAV（16 / 24 / 32 位 PCM、32 位浮点）、WAVE_FORMAT_EXTENSIBLE、带 `bext`、`iXML` 和 `JUNK` 块的 Broadcast WAV（Pro Tools）、RF64、Wave64、AIFF、CAF（Logic Pro 录音）和 FLAC；单声道话筒的单声道与立体声导出。采样率 44.1–192 kHz。DAW 以错误速度播放的扫频（未转换的采样率或时间伸缩）会被诊断出来（[MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §2b）。

## DAW

Pro Tools、Logic Pro、GarageBand、Cubase / Nuendo、Fender Studio Pro（Studio One）、Ableton Live、REAPER、FL Studio、Bitwig Studio、Digital Performer 和 Audacity 的分步说明，以及适用于其他任何 DAW 的检查清单，见 [user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md)。它们依据各厂商的文档编写，每一步都注明来源（少数第三方来源已标出）：属于按文档编写的流程。**还没有任何 DAW 在真实硬件上配合 ReverbScope 运行过**；[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md) 中的逐个 DAW 矩阵是空的。

## 音频系统（主机 API，独立模式）

PortAudio 提供的每一种主机 API 都会被列出和探测（`reverbscope devices --probe`）：Windows 上有 MME、DirectSound、WASAPI（共享模式，或用 `--wasapi-exclusive` 打开独占模式）、WDM-KS，以及存在时的 ASIO；macOS 上是 Core Audio（用 `--coreaudio-set-rate` 避免转换）；Linux 上是 ALSA（`hw:` 和插件设备）、JACK 和 OSS。输入与输出保持在同一种主机 API 上，播放前检查声道，使用两个独立设备时给出警告。各主机 API 的行为及出处见 [AUDIO_DEVICES.zh-CN.md](AUDIO_DEVICES.zh-CN.md)。已用模拟的设备表（`tests/unit/test_audio_inventory.py`）和合成后端验证；**尚未用真实音频接口验证**。

## 跨平台行为

2026-09-24 审查，并用模拟对应平台的测试修复（`tests/unit/test_cross_platform.py`）：Windows 上命令行输出经管道时使用 UTF-8、可移植的 `project.json` 路径、大小写不敏感的文件系统（已在 macOS 和 Windows CI 运行器上确认）、Windows 上两个进程同时写日志时的日志轮转、Windows 显示语言和 `zh-Hans` 区域标记、Windows 无法转换的日期、写在会话自身文件夹内的会话打包文件。包内所有文件读写都显式传入 `encoding="utf-8"`（用 `-X warn_default_encoding` 检查）；非 ASCII 路径可以正常使用（在 Windows 上 libsndfile 用宽字符 API 打开这些路径）。
