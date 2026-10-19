[English](README.md) | **简体中文**

# ReverbScope

ReverbScope 用来在录音之前判断一个房间和一个话筒位置能不能用。它通过音箱播放一段指数正弦扫频，用测量话筒录下来，
解出房间脉冲响应，并报告混响（EDT、T20、T30、RT60）、清晰度（C50、C80、D50）、早期反射、本底噪声和频率响应，
每个数字都带单位和有效性标记。面向录音师、家庭和小型工作室的录音者，以及学习房间声学的人。完全离线，可以配合任何
DAW 使用，也可以单独使用；有桌面应用和命令行，支持英文和简体中文。许可证为 Apache-2.0。

**状态：预发布。** 分析核心、桌面应用和命令行在 Linux、macOS、Windows 上都有自动化测试覆盖。但还没有任何一次经过
真实音频接口或 DAW 的测量被报告过，硬件验证尚未开始；在[硬件测试矩阵](docs/HARDWARE_TESTS.zh-CN.md)有记录之前，
请把所有数值当作未经验证的结果。

[![CI](https://github.com/jingyemingyue/ReverbScope/actions/workflows/ci.yml/badge.svg)](https://github.com/jingyemingyue/ReverbScope/actions/workflows/ci.yml)
[![最新预发布版](https://img.shields.io/github/v/release/jingyemingyue/ReverbScope?include_prereleases&label=pre-release)](https://github.com/jingyemingyue/ReverbScope/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

![main 上的 ReverbScope 桌面应用：一个话筒位置的概览，包括混响、本底噪声、早期反射和直达声、测量健康度和分频带表格，右侧是检查器（合成演示数据）](docs/images/gui-results.zh-CN.png)

<sub>`main` 上的桌面应用（截图时为 0.5.0b3），打开的是 `reverbscope demo` 生成的会话。合成演示数据，没有测量真实房间。</sub>

> 本文是 [README.md](README.md) 的简体中文版本；两者不一致时，以英文版为准。

## 更新日志

完整记录见 [CHANGELOG.md](CHANGELOG.md)（英文）。

* **`main` 上（未发布）：** 桌面应用改为一个工作台窗口：测量列表；总览、频率响应、脉冲响应、衰减、噪声、语谱图、
  瀑布图、房间、对比和报告等视图；检查器；底部测量条。图表可以缩放、平移、带单位读数，并导出 PNG、SVG 或 CSV。
  **帮助 → 发送反馈…** 和 **报告问题…** 会打开预先填好信息的 GitHub issue 表单。
* **0.5.0b4（2026-10-18）：** 在 0.5.0b3 基础上整理文档和发布说明。
* **0.5.0b3（2026-10-09）：** 每个结果都附带测量健康度（对这次录音本身的检查，每项都写明原因和下一步）；两个位置
  对比时给出判定；多个位置的项目总览；终端里的方框报告；交互式 `reverbscope` 菜单。

0.5.0b2 到 0.5.0b4，以及 0.5.0rc1 / rc2 目前都只是 Draft 版本。**公开**的最新预发布版是
[v0.5.0b1](https://github.com/jingyemingyue/ReverbScope/releases/tag/v0.5.0b1)（2026-10-01），发布时项目还叫 **RoomScope**。

## 下载与安装

安装包附在 [GitHub Releases](https://github.com/jingyemingyue/ReverbScope/releases) 上。它们是预发布版本，不是稳定版。
每个安装包都自带 Python 和全部依赖，不需要另外安装 Python。

**现在能下载的：** 旧名下的 v0.5.0b1。它的文件名和命令以 `RoomScope` / `roomscope` 开头，而不是
`ReverbScope` / `reverbscope`；[公开 beta 安装指南](docs/PUBLIC_TESTING.zh-CN.md)列出了这些文件、校验和与首次启动步骤。
下面的表格是更名后的文件名；从 0.5.0b2 起的每个版本都带这些文件，维护者公开发布后即可下载。

### 🖥 桌面版（Desktop Edition）

桌面应用加 `reverbscope` 命令行，适合绝大多数用户。

| 平台 | 文件 | 架构 | 安装 |
| --- | --- | --- | --- |
| macOS 14 及更新 | `ReverbScope-Desktop-macOS-arm64.dmg` | Apple 芯片 | 打开 DMG，把 **ReverbScope** 拖到 **应用程序** |
| macOS 14 及更新 | `ReverbScope-Desktop-macOS-x86_64.dmg` | Intel | 同上 |
| Windows 10 / 11 | `ReverbScope-Desktop-Windows-x64-Setup.exe` | x64 | 运行安装程序，然后从开始菜单打开 **ReverbScope** |
| Windows 10 / 11 | `ReverbScope-Desktop-Windows-x64.zip` | x64 | 全部解压，运行 `reverbscope-gui.exe` |
| Linux（glibc 2.39 及更新） | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | x86_64 | 解压后运行 `reverbscope/reverbscope-gui` |

**第一次打开。** 安装包没有签名：没有经过 Apple 公证，也没有 Windows Authenticode 签名，所以系统会警告一次。

* **macOS：** 点 **完成**，再到 **系统设置 → 隐私与安全性 → 仍要打开**。不要关闭 Gatekeeper 或系统完整性保护（SIP），
  不需要这样做。
* **Windows：** SmartScreen → **更多信息 → 仍要运行**。

系统询问麦克风权限时请允许；否则录到的是静音。

### ⌨️ 终端版（Terminal Edition）

同样的测量和分析，只有命令行，没有窗口。适合脚本、服务器和没有图形桌面的电脑。

| 平台 | 文件 | 架构 | 运行 |
| --- | --- | --- | --- |
| macOS 14 及更新 | `ReverbScope-Terminal-macOS-arm64.tar.gz` | Apple 芯片 | `reverbscope-terminal/reverbscope demo` |
| macOS 14 及更新 | `ReverbScope-Terminal-macOS-x86_64.tar.gz` | Intel | `reverbscope-terminal/reverbscope demo` |
| Windows 10 / 11 | `ReverbScope-Terminal-Windows-x64.zip` | x64 | 打开 `ReverbScope Terminal.cmd`，再运行 `reverbscope.exe demo` |
| Linux（glibc 2.39 及更新） | `ReverbScope-Terminal-Linux-x86_64.tar.gz` | x86_64 | `reverbscope-terminal/reverbscope demo` |

在 macOS 上，如果解压出的 `reverbscope` 被拒绝运行，执行一次
`xattr -dr com.apple.quarantine reverbscope-terminal`，它只清除这些文件的下载标记。

### 该选哪个？

| | 桌面版 | 终端版 |
| --- | --- | --- |
| 带图表的桌面应用 | 有 | 无 |
| `reverbscope` 命令行 | 有 | 有 |
| 测量、分析、对比、项目 | 有 | 有 |
| English / 简体中文 | 有 | 有 |

拿不准就选桌面版。每个版本还附带用于核对下载的 `SHA256SUMS`、Python wheel 和源码包。
[安装指南](docs/INSTALLATION.zh-CN.md)介绍校验和、wheel、Linux 系统库、更新、卸载和故障排查。

## 不接设备先试用

`reverbscope demo` 在一个模拟房间上跑完整个流程，不需要话筒和音频接口，也不会播放任何声音。

1. 在程序所在的位置打开终端。下载的安装包不会把 `reverbscope` 加进 `PATH`：Windows 安装程序把它放在
   `%LOCALAPPDATA%\Programs\ReverbScope`；macOS 桌面版的命令是
   `/Applications/ReverbScope.app/Contents/MacOS/ReverbScope`。
2. 运行演示。它模拟两个话筒位置，用和真实测量相同的代码分析、对比，并打印接下来可以试的命令。
   保存的每个会话都标为合成演示。

   ```bash
   reverbscope --lang zh_CN demo --out demo/
   ```

3. 想在桌面应用里看同样的数据，选 **文件 → 打开会话…**，选择演示写出的某个文件夹。桌面应用本身没有演示模式。

![终端里的 reverbscope demo：两个模拟位置的结果、它们的对比和下一步（合成数据）](docs/images/cli-demo.zh-CN.svg)

## 桌面版使用

[用户指南](docs/user-guide/zh-CN.md)逐一介绍每个控件，这里是简要版。

### 第一次打开

窗口分三栏：左边是**测量列表**，中间是**视图**，右边是**检查器**，底部是**测量条**。没有打开任何内容时，
起始面板显示已保存的会话和**首次测量说明**（关闭后可以用 **帮助 → 入门** 重新打开）。视图栏上的 **列表** 和
**检查器** 可以隐藏两侧；**视图 → 重置布局** 回到默认布局。**设置**（Ctrl+, / ⌘,）里可以改语言、
主题（跟随系统、浅色、深色）、默认录音配置、音频后端和默认输出文件夹。

### 选择音频设备

在测量条上选 **音频接口**（由 ReverbScope 播放和录音）或 **DAW 录音**（由 DAW 播放和录音）。用音频接口时，
选择**输入**设备、**采样率**和**话筒通道**；**高级** 里是输出设备和可选的回路通道；**设置…** 打开这种模式的全部设置。
Windows 上优先选接口的 *WASAPI* 或 *WDM-KS* 条目。**帮助 → 用于问题报告的环境报告** 会列出每个设备及其支持的采样率。

### 一步步测量

1. 先把监听音量**调低**。ReverbScope 从不改动系统音量。
2. 摆好话筒和音箱，填写**位置**名称。
3. 按 **开始**（Ctrl+Return）。扫频播放的同时录音；**停止** 或 Esc 立即停止。播放电平高于 −12 dBFS 时，
   需要先在 **设置…** 里勾选确认。
4. 录音分析完成后出现在列表里，标为*未保存*。用 **文件 → 保存会话…**（Ctrl+S）保存。

**DAW 录音** 模式下，**设置…** 会为 DAW 生成测试信号，并导入录好的文件；[DAW 设置说明](docs/user-guide/daw-setup.zh-CN.md)
写了十个 DAW 的具体步骤。

### 看懂结果

每个视图都用列表里的颜色显示选中的测量。Ctrl+1 到 Ctrl+9（macOS 上是 ⌘）切换视图。

| 视图 | 看什么 |
| --- | --- |
| 总览 | 带有效性的关键数值、测量健康度和倍频程表格（EDT、T20、T30、RT60、C50、C80、D50、中心时间） |
| 频率 | 幅频响应，图上注明显示平滑；设了基准时多一个差值图 |
| 时间 | 脉冲响应和能量时间曲线，标出早期反射；点击某个反射可以选中它 |
| 衰减 | 各频带的 Schroeder 衰减曲线，阴影标出评估范围 |
| 频谱 | 语谱图、瀑布图（累积频谱衰减）和带工频哼声候选的噪声频谱 |
| 房间 | 你输入的房间尺寸和测量能约束的范围；单个话筒无法判断是哪面墙，它也不会这样标注 |
| 报告 | 完整的文字报告，可以用 **复制报告** 复制 |

**检查器** 显示当前测量的健康度（发现了什么、影响哪些数值、下一步怎么做）、带可信度标签的关键数值和选中的反射。

### 对比位置

测量或打开两次录音，在列表里右键其中一个，选 **设为基准**，再选中另一个并打开 **对比**：它按方面（混响、清晰度、
早期反射、本底噪声、低频）给出判定，并画出差值图。**项目…** 把同一个房间的录音按位置归在一起，并给出总览和下一步该测什么。

### 保存、导出与报告

* 每个图表上的 **导出** 可以保存 PNG、SVG，或把画出的曲线存成 CSV。
* **坐标轴…** 设置精确范围；**适配**、R 键或双击恢复默认。
* 保存的会话文件夹里有 `result.json`、`impulse_response.wav`、`session.json` 和录音；会话包和命令行 CSV 导出见
  [用户指南](docs/user-guide/zh-CN.md)。

## 功能

以下功能已在 `main` 上实现，并有使用合成数据的自动化测试：

* **两种测量方式。** *独立模式*：ReverbScope 通过你选择的接口播放和录音（经 `sounddevice` 使用 PortAudio）。
  *通用 DAW 模式*：DAW 播放扫频并录下话筒，ReverbScope 读取导出的文件（WAV、Broadcast WAV、RF64、Wave64、AIFF、CAF、FLAC），
  从不和 DAW 直接通信。
* **分析。** 指数正弦扫频和反卷积；各倍频程的 EDT、T20、T30 和 RT60 估计；C50、C80、D50 和中心时间；频率响应；
  本底噪声和工频哼声；早期反射；低频共振候选。
* **测量健康度。** 检查这次录音本身（扫频、播放速度、直达声、电平、失真、掉帧、衰减范围、本底噪声、录音长度），
  每项为良好、警告、无效或未知，并写明原因和下一步。
* **对比与项目。** 两次录音之间按方面给出判定；一个房间多个位置的项目总览。不做排名。
* **如实的数字。** 每个数值都带单位和有效性标记。电平用 dBFS（未校准）。数据不足以给出某个数值时，ReverbScope 会说明原因，
  而不是估一个。没有房间评分。
* **录音配置**（人声、旁白、原声吉他、鼓、房间话筒、合唱）只调整建议，不改变测量。
* **桌面应用和命令行** 的数字和用词一致；英文和简体中文；浅色和深色主题。
* **离线。** 不联网，没有账号，没有遥测。

ReverbScope 和 REW、Open Sound Meter、ARTA、Smaart 等工具的区别，以及什么情况下其他工具更合适：
[docs/COMPARISON.zh-CN.md](docs/COMPARISON.zh-CN.md)。

## 系统与硬件要求

* **电脑：** macOS 14 及更新（Apple 芯片或 Intel）、Windows 10 / 11 x64，或 glibc 2.39 及更新的 Linux x86_64。
  用 wheel 或源码安装需要 Python 3.12 及更新版本。
* **音频接口**：至少一路输入和一路输出；或者一个能播放和录制 WAV 的 DAW。只能通过 ASIO 工作的接口请用通用 DAW 模式，
  因为安装包不带 ASIO 支持。
* **话筒：** 全指向测量话筒的结果最有意义。没有校准时，电平保持为 dBFS。
* **音箱：** 一只监听音箱或扬声器用来播放扫频。
* **可选：** 一根回路线，从驱动音箱的那路输出接到第二路输入，在话筒旁边同时录下播放链路的电信号参考。

哪些系统、DAW 导出格式和主机 API 经过了验证，以及怎样验证的：[docs/COMPATIBILITY.zh-CN.md](docs/COMPATIBILITY.zh-CN.md)。

## 命令行

桌面版、终端版和 Python 安装都包含 `reverbscope`。在终端里不带子命令运行 `reverbscope` 会打开交互式菜单。

```bash
# 通用 DAW 模式：生成测试信号，在 DAW 里录音，然后分析
reverbscope sweep --out sweep_48k.wav
reverbscope analyze --recording recording.wav --sweep sweep_48k.wav --out results/

# 独立模式：列出设备，然后测量
reverbscope devices
reverbscope measure --out session1/ --input-device 2 --output-device 3

# 查看和对比已保存的会话
reverbscope show results/
reverbscope compare results/ session1/ --same-input-gain

# 一个房间的多个位置
reverbscope project init --out room/ --name Booth
reverbscope project add room/ session1/ --position desk
reverbscope project overview room/

# 用于问题报告的环境报告
reverbscope doctor --probe
```

所有命令和选项见 `reverbscope --help` 和[用户指南](docs/user-guide/zh-CN.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [安装指南](docs/INSTALLATION.zh-CN.md) | 各平台安装、校验和、Python、更新、故障排查 |
| [用户指南](docs/user-guide/zh-CN.md) | 测量、看懂结果、对比、项目、导出 |
| [DAW 设置](docs/user-guide/daw-setup.zh-CN.md) | 十个 DAW 的分步说明 |
| [测量方法](docs/MEASUREMENT_METHODOLOGY.md) | 算法、单位、有效性规则、参考文献（英文） |
| [音频设备](docs/AUDIO_DEVICES.zh-CN.md) | 主机 API，以及如何探测设备 |
| [项目状态](docs/STATUS.md) | 已实现、已测试和缺失的内容（英文） |
| [路线图](docs/ROADMAP.zh-CN.md) | 接下来做什么 |
| [架构](docs/ARCHITECTURE.md) | 包结构和数据流（英文） |
| [文档索引](docs/index.zh-CN.md) | 其他所有文档 |

## 从源码构建

需要 Python 3.12 及更新版本。ReverbScope 还没有发布到 PyPI。

```bash
git clone https://github.com/jingyemingyue/ReverbScope.git
cd ReverbScope
python3.12 -m venv .venv && source .venv/bin/activate   # Windows：.venv\Scripts\activate
pip install -e ".[dev,gui]"
reverbscope --help
reverbscope gui
```

Linux 上还需要 PortAudio（`libportaudio2`）和[安装指南](docs/INSTALLATION.zh-CN.md#linux)里列出的 Qt 系统库。
`scripts/build_release.py` 用 PyInstaller 为当前平台构建两个版本；Windows 安装程序用 Inno Setup 生成，macOS 磁盘映像由
`packaging/macos/make_dmg.sh` 生成。发布工作流（`.github/workflows/release.yml`）在 GitHub 的运行器上构建全部安装包。

### Python API

```python
from reverbscope import analyze
from reverbscope.io.wav import load_reference, read_wav

result = analyze(read_wav("recording.wav"), load_reference("sweep_48k.wav"))
print(result.decay.broadband.rt60_estimate_s, result.decay.broadband.rt60_basis)
```

API 和文件格式的稳定性规则见 [docs/API_STABILITY.md](docs/API_STABILITY.md)（英文）。

## 测试

```bash
ruff check . && ruff format --check .
mypy --platform linux
python scripts/check_doc_links.py && python scripts/check_cli_docs.py && python scripts/check_src_safety.py
QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85
```

CI 在 Ubuntu 上用 Python 3.12、3.13、3.14，在 macOS 和 Windows 上用 Python 3.12 运行测试，另外还有代码检查、类型检查、
sdist 和 wheel 构建，以及许可证包检查。测试使用合成信号和伪音频后端，不算硬件测试。

## 反馈

* 在桌面应用里：**帮助 → 发送反馈…** 或 **帮助 → 报告问题…** 会打开 GitHub issue 表单，并填好版本和系统信息。
  应用本身不发送任何内容。
* 在 GitHub 上：[选择一个 issue 表单](https://github.com/jingyemingyue/ReverbScope/issues/new/choose)
  （缺陷、测量问题、提问或反馈、功能请求、音频接口或 DAW 测试报告）。[SUPPORT.zh-CN.md](SUPPORT.zh-CN.md) 说明该用哪个表单、需要附上什么。
* 安全问题：按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md) 私下报告。

## 参与贡献

现在最有用的贡献，是在真实音频接口或真实 DAW 上跑一次，无论成功还是失败。[测试指南](docs/COMMUNITY_TESTING.zh-CN.md)
写明了要运行什么，结果汇总在 [docs/HARDWARE_TESTS.zh-CN.md](docs/HARDWARE_TESTS.zh-CN.md)。

贡献代码和文档前，请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和[行为准则](CODE_OF_CONDUCT.md)（英文）。适合新手的小任务见
[docs/COMMUNITY_TASKS.md](docs/COMMUNITY_TASKS.md)。项目如何使用和审阅 AI 辅助：[docs/AI_ASSISTANCE.md](docs/AI_ASSISTANCE.md)。

## 许可证与第三方声明

ReverbScope 采用 Apache License 2.0，见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。仓库里没有内置第三方源代码
（[docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md)）。所有依赖及其许可证列在 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。
桌面版通过 PySide6 Essentials 以 LGPL-3.0 使用 Qt；每个安装包都在 `THIRD_PARTY_LICENSES` 中附带所含组件的许可证文本
（也可以从 **帮助 → 第三方许可证…** 打开）。

## 致谢

所用方法来自公开发表的工作：A. Farina（2000）的指数正弦扫频，M. R. Schroeder（1965）的反向积分，A. Lundeby 等人（1995）
的截断点，以及 ISO 3382-1 / -2 的房间声学参数。ReverbScope 基于 NumPy、SciPy、soundfile（libsndfile）、sounddevice（PortAudio）、
PySide6（Qt）、pyqtgraph 和 matplotlib 构建。完整参考文献见 [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md)。

## 维护者

ReverbScope 由 [@jingyemingyue](https://github.com/jingyemingyue) 维护。
