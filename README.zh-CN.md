[English](README.md) | **简体中文**

# RoomScope

**用扫频测量你的录音房间，判断一个话筒位置能不能用——可以配合任何 DAW，也可以单独使用。**

[![下载](https://img.shields.io/github/v/release/jingyemingyue/RoomScope?include_prereleases&label=download&color=1a7f8e)](https://github.com/jingyemingyue/RoomScope/releases)
[![CI](https://github.com/jingyemingyue/RoomScope/actions/workflows/ci.yml/badge.svg)](https://github.com/jingyemingyue/RoomScope/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

> 本文是 [README.md](README.md) 的简体中文版本；两者不一致时，以英文版为准。

![RoomScope 结果总览：RT60、本底噪声、早期反射、直达声和各倍频带混响](docs/images/results-overview.png)

<sub>内置演示的结果页（合成房间，不需要音频接口；截图为英文界面，程序可切换为简体中文）。</sub>

## 下载

### **[→ 从 GitHub Releases 下载 RoomScope](https://github.com/jingyemingyue/RoomScope/releases)**

免费、开源。在该页面最上方的最新版本里，展开 **Assets**，按你的电脑选择文件：

| 你的电脑 | 下载哪个文件 | 然后 |
| --- | --- | --- |
| Apple 芯片（M1 及更新）的 **Mac**，macOS 14+ | `RoomScope-macos-arm64.dmg` | 打开 DMG，把 **RoomScope** 拖到 **Applications（应用程序）**，再从“应用程序”里打开 |
| Intel 处理器的 **Mac**，macOS 14+ | `RoomScope-macos-x86_64.dmg` | 同上 |
| **Windows** 10 / 11，64 位 | `RoomScope-setup.exe`（安装程序） | 运行它，然后从开始菜单打开 **RoomScope** |
| | 或 `roomscope-windows-x64.zip`（免安装） | 右键 → **全部解压缩…**，打开解压出的文件夹，双击 **`roomscope-gui.exe`** |
| **Linux** x86_64 | `roomscope-linux-x86_64.tar.gz` | 解压后运行 `roomscope/roomscope-gui` |

不确定是哪种 Mac？苹果菜单 → **关于本机**：显示 *芯片 Apple M…* 的是 Apple 芯片，显示
*处理器 Intel* 的是 Intel。

> **当前构建是未签名的开发版 / 预发布版构建。** 它们没有经过 Apple 公证，也没有 Windows
> Authenticode 签名，所以第一次打开时系统会警告：
>
> * **macOS** 会提示 Apple 无法验证 RoomScope。点 **完成**，打开 **系统设置 → 隐私与安全性**，
>   向下滚动，在关于 RoomScope 的提示旁点 **仍要打开**，再确认一次。只需要做一次。
>   不需要、也不应该关闭 Gatekeeper 或系统完整性保护（SIP）。
> * **Windows** SmartScreen 可能提示“Windows 已保护你的电脑”：点 **更多信息 → 仍要运行**。
>
> 完整步骤（含校验和、更新、卸载和故障排查）：**[安装指南](docs/INSTALLATION.zh-CN.md)**。

> **尚未经过任何真实硬件验证。** 目前没有记录过任何一次使用真实音频接口或真实 DAW 的检查；
> 迄今为止的所有测试要么基于合成数据，要么运行在 CI 机器上。在 0.5.0 之前，请把所有数字视为
> 未经验证，也欢迎[帮助测试](#帮助测试-04x-预发布版本)。

### 开发者

需要 Python 3.12 或更新版本。RoomScope 还没有发布到 PyPI，请从克隆的仓库安装：

```bash
git clone https://github.com/jingyemingyue/RoomScope.git
cd RoomScope
python3.12 -m venv .venv && source .venv/bin/activate   # Windows：.venv\Scripts\activate
pip install -e ".[dev,gui]"
roomscope --help
roomscope gui
```

每个发布版本还附带 wheel（`roomscope-<version>-py3-none-any.whl`）和源码包，见
[安装指南 → Python](docs/INSTALLATION.zh-CN.md#python-wheel-和源码包)。

## 第一次测量

1. 打开 RoomScope，点 **演示（无需音频接口）**：不播放任何声音，就能看到一份完整的合成房间结果。
2. 先把监听音箱音量**调低**。RoomScope 不会改动系统音量。
3. 正式测量，二选一：
   * **独立模式**——选择你的音频接口，由 RoomScope 自己播放扫频并录制测量话筒。
   * **通用 DAW 模式**——RoomScope 生成扫频 WAV；在 DAW 中播放并录音，导出录音后再载入
     （[DAW 说明](docs/user-guide/daw-setup.zh-CN.md)）。
4. 查看结果：混响（EDT / T20 / T30 / RT60）、频率响应、本底噪声、早期反射和低频共振，每一项都带
   有效性标记。用 **对比** 比较两个话筒位置。

[用户指南](docs/user-guide/zh-CN.md)（[English](docs/user-guide/en.md)）逐页说明各项功能。

## 这是什么

RoomScope 是一个开源、不依赖任何 DAW 的录音环境分析工具。它回答录音师面对一个房间和一个话筒位置
时会问的实际问题：

* 这个房间能不能用来录音？
* 这个位置有哪些声学问题（强早期反射、衰减过长、低频堆积、电源哼声、本底噪声过高）？
* 挪动话筒或演奏者之后，情况有没有改善？

它用指数正弦扫频（ESS）测量房间，通过解卷积得到房间脉冲响应，并报告混响（EDT / T20 /
T30 / 估算的 RT60）、频率响应、本底噪声、早期反射以及可能存在的低频共振。每个数字都带有单位、
算法来源和有效性标记；数据质量不够时，RoomScope 会给出 *“衰减范围不足”*（*Insufficient decay
range*），而不是编造一个数字。RoomScope 有意不提供任何“房间评分”。界面、命令行和报告都有英文和
简体中文。

状态：**0.4.x 预发布版本**，正在向 1.0 推进
（[RELEASE_PLAN.zh-CN.md](docs/RELEASE_PLAN.zh-CN.md)，英文版 [RELEASE_PLAN.md](docs/RELEASE_PLAN.md)）。
DSP 核心、CLI、GUI、对比、回送（loopback）、zh-CN 界面翻译、会话打包和桌面程序包都已实现，
并在 Linux、macOS 和 Windows 上由合成测试覆盖。**尚未完成：** 任何在真实硬件上测得的结果
（硬件矩阵和验证活动都还是空的）、已签名的程序包、PyPI 包。当前可用功能的概况：
[docs/STATUS.md](docs/STATUS.md)。

## 帮助测试 0.4.x 预发布版本

发布 0.4.x 构建，是为了让手上有真实音频接口和 DAW 的人找出哪些地方能用、哪些不能用。检查失败和
检查通过同样有价值。

1. 安装一个构建（见[下载](#下载)；Gatekeeper / SmartScreen 警告属于预期情况）。
2. 打开 RoomScope，先运行一次 **演示（无需音频接口）**（英文界面为 **Demo (no interface)**）：
   它不播放任何声音，只展示一份结果是什么样子。
3. 先把监听音量调低，然后用你的音频接口和一支话筒运行 **独立模式**，或通过你的 DAW 运行
   **通用 DAW 模式**（[DAW 说明](docs/user-guide/daw-setup.zh-CN.md)）。
4. 报告实际情况，并附上 **帮助 → 用于问题报告的环境报告**（英文界面为
   **Help → Environment Report for Bug Reports**）的内容：
   * 音频接口测试报告（[中文表单](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware-zh-CN.yml)
     / [English form](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml)）：
     设备列表、44.1 / 48 / 96 kHz 下的完整测量、2 个以上的声道、回送、播放过程中点“停止”、丢帧、
     测量过程中拔出设备；
   * DAW 兼容性报告（[中文表单](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw-zh-CN.yml)
     / [English form](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml)）：
     通过某一个 DAW 录制并导出的同一段扫频。

结果会连同报告链接一起记入 [docs/HARDWARE_TESTS.zh-CN.md](docs/HARDWARE_TESTS.zh-CN.md)
（英文版 [docs/HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md)）。只有在实体音频接口上完成的测试才会记入
该表。

## 两种工作流程，同一个分析核心

### 通用 DAW 模式

适用于任何能导入、播放、录制和导出 WAV 文件的 DAW。RoomScope 从不与 DAW 通信。它读取 DAW 导出的
文件（Broadcast WAV、RF64、Wave64、AIFF、CAF、FLAC；16/24/32 位 PCM 或 32 位浮点；单声道或多声道）；
在使用扫频的附属文件（sidecar）时，如果 DAW 以错误的速度播放了扫频，它会指出常见原因（工程采样率
与扫频不同，或 Warp / Flex / Follow Tempo 造成的伸缩超出了估计值本身的离散范围：默认 10 s 扫频约为
1.3 %，扫频越短，该范围越大）。
我们根据各厂商的文档编写了分步说明，涵盖 Pro Tools、Logic Pro / GarageBand、Cubase / Nuendo、
Fender Studio Pro（Studio One）、Ableton Live、REAPER、FL Studio、Bitwig、Digital Performer 和
Audacity：[docs/user-guide/daw-setup.zh-CN.md](docs/user-guide/daw-setup.zh-CN.md)
（英文版 [docs/user-guide/daw-setup.md](docs/user-guide/daw-setup.md)）。
**这些 DAW 目前都还没有在真实 DAW 中与 RoomScope 一起实际运行过**
（[HARDWARE_TESTS.zh-CN.md](docs/HARDWARE_TESTS.zh-CN.md)）；提交一份 DAW 兼容性报告是你能做的最有用的贡献。

1. **生成测试信号** —— RoomScope 写出一个扫频 WAV（外加一个记录扫频精确参数的小 JSON 附属文件）。
2. **在 DAW 中录音** —— 把 WAV 导入一条轨道，通过音频接口和监听音箱播放，在另一条轨道上录制测量话筒。
3. **导入录音** —— 把录好的轨道导出为 WAV（采样率与工程相同；长度不限，无需裁切）。
4. **分析** —— RoomScope 自动找到扫频，完成解卷积并生成报告。

### 独立模式

RoomScope 通过你选择的音频接口自己播放扫频并录制话筒（经 `sounddevice` 调用 PortAudio）。开始时请把
监听音量调低：默认扫频电平比较保守，而且 RoomScope 不会改动系统音量或音频设置（唯一的例外需要用户
主动开启：macOS 上一个设置设备采样率的选项，说明见
[SECURITY.zh-CN.md](SECURITY.zh-CN.md) 中关于独立模式安全性的一节；英文版
[SECURITY.md](SECURITY.md#safety-of-standalone-mode)）。

两种模式调用的是完全相同的分析流程（`roomscope.core.pipeline.analyze`）。

## 命令行

同样的分析也可以用命令行完成。Python 安装和 Windows / Linux 程序包里的命令是 `roomscope`
（与 `roomscope-gui` 在同一文件夹）；macOS 上是 `/Applications/RoomScope.app/Contents/MacOS/RoomScope`。

```bash
# 1. 生成测试信号（48 kHz，20 Hz–20 kHz，10 s 扫频，-12 dBFS）
roomscope sweep --out sweep_48k.wav

# 2. 在 DAW 中播放它，录制话筒，导出 recording.wav

# 3. 分析
roomscope analyze --recording recording.wav --sweep sweep_48k.wav --out results/

# 可选：用卷尺量两个距离，即可得到垂直方向的几何信息
roomscope analyze --recording recording.wav --sweep sweep_48k.wav \
  --speaker-distance 1.65 --mic-height 0.40 --temperature 21

# 可选：按录音类型解读结果（generic | vocal | voiceover |
# acoustic_guitar | drums | room_mic | choir）
roomscope analyze --recording recording.wav --sweep sweep_48k.wav --profile voiceover

# 重新打开已保存的会话（报告相同；--profile 会覆盖保存时的配置）
roomscope show results/
roomscope show results/ --list

# 对比两个已保存的会话（每个差值都带有效性）
roomscope compare results/ position-b/ --same-input-gain
roomscope schema result

# 双声道 DAW 导出：话筒 + 电回送
roomscope analyze --recording take.wav --sweep sweep_48k.wav --channel 0 --loopback-channel 1

# 独立模式：先列出设备，再测量（可选：在输入 2 上接回送）
roomscope devices
roomscope measure --out session1/ --input-device 2 --output-device 3 \
  --input-channels 1,2 --loopback-channel 2 --sample-rate 48000

# 演示 / CI：不需要音频接口
roomscope --backend fake measure --out demo/ --duration 2 --post-silence 1.5

# 语言、打包、CSV、项目
roomscope --lang zh_CN analyze --recording take.wav --sweep sweep.wav
roomscope session bundle session1/ --no-audio --out report.zip
roomscope export session1/ --format csv --out curves/
roomscope project init --out room/ --name Booth
roomscope project add room/ session1/ --position desk
roomscope project average room/

# GUI（需要 gui 附加依赖）
roomscope gui
```

`--speaker-distance` 是扬声器到话筒振膜的直线距离；`--mic-height` 是振膜到其下方第一个坚硬水平面的
高度。两者都给出时，RoomScope 会报告扬声器高度、设备上方的反射平面以及水平间距。它**不报告坐标、
不报告房间的长度或宽度，也从不指认是哪一面墙**：单只全指向话筒在单一位置上测到的是路径长度，而不是
方向；即使提供了距离，几何关系仍然缺少两个约束，无法确定。结果 JSON 中也记录了这一论证。

`--profile` 决定如何把测得的数字转换为建议（默认 `generic`；`vocal`、`voiceover`、`acoustic_guitar`、
`drums`、`room_mic` 和 `choir` 各有针对该类录音的阈值和措辞）。报告会在 `Interpretation`（解读）旁边
标出配置名称，以免有人把这些建议误当成与录音用途无关的客观结论。GUI 在两种测量模式中都提供同样的选择。

`results/` 中会生成 `result.json`（全部指标和曲线）、`impulse_response.wav`（原始脉冲响应，float32）
和 `session.json`（测量元数据）。原始录音永远不会被修改。`roomscope show` 以及 GUI 中的
**打开会话**（**Open Session**）和主页的会话列表都可以重新打开该目录；脉冲响应 WAV 是权威的采样记录
（`result.json` 保存的是指标，不保存脉冲响应的采样）。最近打开或保存过的会话记录在 `$ROOMSCOPE_HOME`
下（默认为 `~/.roomscope`）。

## Python API

```python
from roomscope import analyze, compare, interpret_comparison
from roomscope.io.wav import read_wav, load_reference
from roomscope.core import Reference

recording = read_wav("recording.wav")
reference = load_reference("sweep_48k.wav")  # 如果存在 JSON 附属文件，则使用它
result = analyze(recording, reference)
print(result.decay.broadband.rt60_estimate_s, result.decay.broadband.rt60_basis)
for r in result.reflections.reflections:
    print(f"{r.delay_ms:.1f} ms  {r.relative_db:.1f} dB")
```

## RoomScope 有什么不同

* **它拒绝编造数字。** 每个指标都带有单位、算法来源和有效性标记；衰减太短、不足以计算 T30 时，
  它给出 *衰减范围不足*，而不是一个数字。它不提供任何单一的“房间评分”。
* **它在 DAW 旁边工作，而不是在 DAW 里面。** 它只需要一个能播放和录制 WAV 的 DAW；当 DAW 以错误的
  速度播放扫频时，它会指出常见原因（采样率不匹配，或 Warp / Flex / Follow Tempo）。各 DAW 的操作步骤
  已写成文档，但尚未在每个 DAW 中实际测试。
* **它回答录音师真正关心的问题** —— “这个位置适合录人声、做鼓的房间话筒、录合唱吗？” —— 方式是带有
  明确标签的解读配置；它还能对比两个位置，每个差值都带有有效性。
* **它会说明一支话筒无法知道什么。** 摆位几何从不指认某一面墙，也不推导测量无法支撑的坐标。

与其他工具的比较（附来源）见 [docs/COMPARISON.zh-CN.md](docs/COMPARISON.zh-CN.md)
（英文版 [docs/COMPARISON.md](docs/COMPARISON.md)）。

## 设计原则

* **不依赖 DAW** —— 永远不使用任何 DAW SDK。输入 WAV，输出 WAV。
* **核心优先** —— DSP 函数是纯 NumPy/SciPy 函数，不依赖 GUI、设备或文件格式，因此 CLI、桌面程序、
  插件或 Python API 都可以共用它们。
* **科学正确性优先于功能** —— 算法来自已发表的论文和标准（Farina 2000、Schroeder 1965、Lundeby 1995、
  ISO 3382-1/-2 等）；见 [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md)。
* **诚实的数字** —— 未经校准时一律使用 dBFS，每个指标都有有效性标记，不提供伪科学的房间评分。
* **净室实现与许可证规范** —— 不内置任何第三方源代码（[docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md)）；
  每一项依赖和每一个参考过的代码仓库都经过审查
  （[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)、
  [docs/THIRD_PARTY_REVIEW.md](docs/THIRD_PARTY_REVIEW.md)）。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/INSTALLATION.zh-CN.md](docs/INSTALLATION.zh-CN.md) | 在 macOS、Windows、Linux 上下载安装或用 Python 安装；更新、卸载、未签名构建的警告、故障排查；[English](docs/INSTALLATION.md) |
| [docs/index.md](docs/index.md) | 文档索引 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 包结构、数据流、扩展点 |
| [docs/ARCHITECTURE_V1.md](docs/ARCHITECTURE_V1.md) | 正在执行的 v1.0 设计：API 分层、对比、回送、打包、国际化、验证关卡 |
| [docs/ARCHITECTURE_V1.zh-CN.md](docs/ARCHITECTURE_V1.zh-CN.md) | v1.0 设计的中文摘要 |
| [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md) | 算法、单位、有效性规则、参考文献 |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | 每一项运行时/开发依赖的许可证和用途 |
| [docs/THIRD_PARTY_REVIEW.md](docs/THIRD_PARTY_REVIEW.md) | 对研究过的外部代码仓库的审查 |
| [docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md) | 任何改编或复制代码的来源记录（目前没有） |
| [docs/LICENSE_DECISION.md](docs/LICENSE_DECISION.md) | RoomScope 为什么采用 Apache-2.0 |
| [docs/STATUS.md](docs/STATUS.md) | 已实现 / 已测试 / 已知限制 / 下一个里程碑 |
| [docs/RELEASE_PLAN.zh-CN.md](docs/RELEASE_PLAN.zh-CN.md) | 发布计划（中文摘要）；[English](docs/RELEASE_PLAN.md) |
| [docs/HARDWARE_TESTS.zh-CN.md](docs/HARDWARE_TESTS.zh-CN.md) | 硬件与 DAW 测试矩阵；[English](docs/HARDWARE_TESTS.md) |
| [docs/user-guide/zh-CN.md](docs/user-guide/zh-CN.md) | 用户指南（简体中文）：安装、测量、读结果、对比、打包 |
| [docs/user-guide/en.md](docs/user-guide/en.md) | User guide (English) |
| [docs/AUDIO_DEVICES.zh-CN.md](docs/AUDIO_DEVICES.zh-CN.md) | 音频系统（主机 API：WASAPI、WDM-KS、MME、Core Audio、ALSA、JACK 等），各自对测量有什么影响，以及 RoomScope 如何探测和选择设备，附来源；[English](docs/AUDIO_DEVICES.md) |
| [docs/COMPATIBILITY.zh-CN.md](docs/COMPATIBILITY.zh-CN.md) | 平台、Python 与依赖的最低版本、DAW 导出格式、音频系统，以及每一项的验证方式；[English](docs/COMPATIBILITY.md) |
| [docs/EDITIONS.zh-CN.md](docs/EDITIONS.zh-CN.md) | 开发者版与安装包版；[English](docs/EDITIONS.md) |
| [docs/COMPARISON.zh-CN.md](docs/COMPARISON.zh-CN.md) | RoomScope 与 REW、Open Sound Meter、ARTA、Smaart、SoundID 等工具的区别，以及什么情况下其他工具更合适；[English](docs/COMPARISON.md) |
| [docs/user-guide/daw-setup.zh-CN.md](docs/user-guide/daw-setup.zh-CN.md) | DAW 分步说明（Pro Tools、Logic、Cubase、Studio One、Live、REAPER、FL Studio、Bitwig、Audacity）；[English](docs/user-guide/daw-setup.md) |
| [docs/PROJECT_BRIEF.zh-CN.md](docs/PROJECT_BRIEF.zh-CN.md) | 最初的项目简介（中文） |

## 参与贡献

这是面向其他开发者阅读、克隆和审查的版本。请先运行 [CONTRIBUTING.md](CONTRIBUTING.md) 中列出的检查，
然后欢迎提交 pull request。也请阅读[行为准则](CODE_OF_CONDUCT.md)。

提交 issue 时可以用中文表单，也可以用英文表单：

| 用途 | 中文表单 | 英文表单 |
| --- | --- | --- |
| 程序崩溃、报错或行为异常 | [问题报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug-zh-CN.yml) | [Bug report](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug.yml) |
| 某个数字看起来不对，或有效性标记出乎意料 | [测量问题](https://github.com/jingyemingyue/RoomScope/issues/new?template=measurement-zh-CN.yml) | [Measurement problem](https://github.com/jingyemingyue/RoomScope/issues/new?template=measurement.yml) |
| 对测量、CLI、GUI 或文档的改进建议 | [功能建议](https://github.com/jingyemingyue/RoomScope/issues/new?template=feature-zh-CN.yml) | [Feature request](https://github.com/jingyemingyue/RoomScope/issues/new?template=feature.yml) |
| 用真实声卡或音频接口运行过 RoomScope | [音频接口测试报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware-zh-CN.yml) | [Audio interface test report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml) |
| 用通用 DAW 模式通过某个 DAW 测量过 | [DAW 兼容性报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw-zh-CN.yml) | [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml) |

可能被滥用的安全问题请不要公开提交 issue，按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md)
（英文版 [SECURITY.md](SECURITY.md)）中的方式私下报告。

可以从这些地方入手：

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) —— 包结构，以及唯一的分析入口
  （`roomscope.core.pipeline.analyze`）
* [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md) —— 每个指标的算法、单位和有效性规则
* [docs/STATUS.md](docs/STATUS.md) —— 已实现 / 已测试 / 下一个里程碑
* `examples/synthetic_measurement.py` —— 不需要硬件的端到端运行示例

```bash
pytest
ruff check . && ruff format --check .
mypy
```

每次 push 和 pull request 都会运行 CI（Ubuntu 上 Python 3.12–3.14 以及 macOS/Windows 上 Python 3.12
的 pytest、ruff、mypy、sdist/wheel 构建）。

## 许可证

Apache License 2.0 —— 见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
