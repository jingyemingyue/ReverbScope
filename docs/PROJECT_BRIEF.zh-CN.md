# ReverbScope 项目需求书（原文存档）

> 本文件是项目发起人在 2026-09-17 的 Cowork 会话中给出的原始需求，逐字保留，作为项目范围与优先级的权威来源。
> 英文架构文档见 `ARCHITECTURE.md`，实现状态见 `STATUS.md`。
>
> 第二节中的 GitHub 托管规则（默认 Private、未明确同意前不公开仓库、不发正式
> Release）记录的是**当时**的初始化约束。面向贡献者的现行规则以仓库根目录的
> `CONTRIBUTING.md`、`SECURITY.md` 和 `CODE_OF_CONDUCT.md` 为准；是否将仓库设为
> Public 由维护者决定，不由本文自动授权。

---

## 一、项目定位与设计原则

你现在是这个开源项目的首席软件架构师、DSP 工程师和实现者。

我要从零创建一个真正可长期维护的开源项目。

项目暂定名称：

ReverbScope

项目定位：

An open-source, DAW-independent recording environment analyzer.

这是一个面向录音师、录音艺术学生、音乐制作人和家庭录音用户的录音环境检测工具。

它的核心目标不是替代专业建筑声学软件，而是回答录音工作中的实际问题：

"这个房间适不适合录音？"
"这个录音位置有什么声学问题？"
"换一个位置以后有没有改善？"
"对于人声、乐器录音而言，这些测量结果意味着什么？"

====================
一、最重要的设计原则

DAW-independent

ReverbScope 不得依赖 Cubase、Pro Tools、Logic、Studio One 或任何特定 DAW。

第一版必须原则上兼容所有能够：

导入 WAV
播放 WAV
录制 WAV
导出 WAV

的主流 DAW。

包括但不限于：

Cubase / Nuendo
Pro Tools
Logic Pro
Studio One
Ableton Live
REAPER
FL Studio
Bitwig
Digital Performer

禁止把核心逻辑写死在任何 DAW SDK 中。

Core-first architecture

声学分析核心必须与：

GUI
音频设备
DAW
文件导入导出

解耦。

未来应能够在同一个 Core 上扩展：

Desktop App
CLI
VST3
AU
AAX
Python API

但 v0.1 暂时不要开发插件。

Scientific correctness over flashy features

对于：

FFT
ESS
deconvolution
impulse response
RT60
RT30
EDT
frequency response
noise analysis
early reflections

不得自己随意发明算法。

优先采用公开、成熟、有文献依据的方法。

任何声学指标都必须明确：

算法来源
单位
计算条件
数据有效性
测量限制

对于无法可靠测量的指标，不得伪造精确结果。

Clean-room implementation when appropriate

可以：

阅读论文
阅读公开标准
阅读第三方项目文档
研究其他项目的架构思路
研究其功能和算法方法

但不得默认：

"GitHub 上能看到代码 = 可以复制代码"。

如果一个算法可以依据公开论文、数学公式或标准独立实现：

优先根据原始论文、标准和公开算法描述进行 clean-room implementation。

不要为了省时间直接复制其他仓库的具体实现。

====================
二、开源许可证与代码来源要求

这是本项目的硬性要求。

任何参考、依赖、复制、修改或移植第三方代码的行为，都必须先完成许可证检查。

不得在 License 不明确的情况下使用第三方代码。

不得假设公开 GitHub 仓库自动允许复制、修改或再发布。

====================
2.1 外部仓库审计

研究任何外部 GitHub / GitLab / SourceForge / Gist / 博客代码之前，记录：

项目名称
Repository URL
作者/组织
当前 commit / tag
License 名称
LICENSE 文件内容
是否存在多个 License
是否存在文件级 License header
是否存在第三方 vendored code
是否存在 NOTICE 文件
是否存在 COPYRIGHT 文件
是否存在 AUTHORS 文件
是否包含专利声明
是否允许修改
是否允许再发布
是否要求署名
是否要求保留版权声明
是否要求公开源代码
是否存在 copyleft
是否影响 ReverbScope 的整体许可证

建立：

docs/THIRD_PARTY_REVIEW.md

所有被实际采用或深度参考的仓库都必须登记。

====================
2.2 无许可证仓库

如果一个仓库：

没有 LICENSE
License 不明确
只有 README 中一句模糊描述
License 文件与源码 header 冲突

则默认：

不得复制其代码。

可以研究：

功能设计
用户界面理念
算法名称
高层架构思想

但实际实现必须独立完成。

并在 THIRD_PARTY_REVIEW.md 中记录：

License unclear — no source code copied.

====================
2.3 Permissive License

对于：

MIT
BSD-2-Clause
BSD-3-Clause
ISC
Apache-2.0

等宽松许可证：

使用前仍需检查具体文本。

如果复制或修改代码：

必须遵守署名、版权声明、NOTICE 等要求。

Apache-2.0 还必须特别检查：

NOTICE
patent clauses
attribution

不得因为"宽松许可证"就删除原作者版权信息。

====================
2.4 Copyleft License

对于：

GPL
AGPL
LGPL
MPL

以及其他 copyleft license：

必须单独评估。

不要自动引入。

首先分析：

static linking
dynamic linking
Python import
subprocess usage
IPC
source modification
distribution model

可能造成的许可证传播影响。

尤其：

GPL / AGPL 代码不得未经分析直接复制进入核心代码库。

如果一个第三方库可能迫使整个 ReverbScope 使用特定 copyleft license：

必须先记录风险，不得自行决定引入。

优先寻找：

permissive alternative
clean-room implementation
独立进程隔离方案

如果仍然需要使用：

在真正引入之前停止并明确记录其许可证影响。

====================
2.5 参考代码 vs 复制代码

必须明确区分：

A. Conceptual reference

只参考：

算法思想
软件功能
架构模式
数学方法

不复制具体源代码。

B. Adapted code

在第三方代码基础上修改。

必须记录来源及 License。

C. Copied code

直接复制第三方实现。

必须：

明确说明来源
遵守 License
保留必要版权信息

D. Independent implementation

根据：

论文
数学公式
标准
自己推导

独立实现。

对于核心 DSP：

优先使用 D。

====================
2.6 禁止来源

不要直接复制：

Stack Overflow 未检查许可证的代码
GitHub issue 中来源不明的代码
Reddit 代码
博客文章代码
教程网站代码
AI 回答中的未知来源代码
无 License GitHub 仓库代码
商业软件反编译代码
商业软件逆向工程获得的实现
泄露源码
proprietary SDK source

除非其授权条款明确允许。

====================
2.7 第三方 Python 包

每个 Python dependency 必须记录：

package
version
homepage
repository
license
purpose
direct / transitive
runtime / dev dependency

建立：

docs/DEPENDENCIES.md

至少审查：

NumPy
SciPy
sounddevice
soundfile
matplotlib
PySide6
pyroomacoustics

以及它们的重要依赖。

注意：

不要只相信 PyPI 页面写的 License。

必要时查看：

官方 repository
LICENSE
packaging metadata

====================
2.8 Qt / PySide6 特别检查

PySide6 / Qt 的许可证结构需要单独确认。

记录：

当前使用版本
LGPL / GPL / commercial licensing 情况
ReverbScope 的分发方式是否满足要求
是否动态链接
是否修改 Qt 本体
最终应用打包时需要附带哪些许可证文件

在正式发布二进制文件之前必须再次检查。

====================
2.9 算法的版权与专利

"算法可以描述"不等于"具体代码可以复制"。

对于 ESS、deconvolution、reverberation measurement 等方法：

优先找到：

原始论文
AES papers
ISO / IEC standards
学术出版物
作者正式技术文档

并根据数学描述独立实现。

如果发现相关专利：

记录：

patent number
jurisdiction
expiration status
practical relevance

不要假设论文公开就意味着专利不存在。

====================
2.10 License provenance

为所有第三方代码建立来源追踪。

如果实际复制或修改任何第三方文件：

必须在：

docs/CODE_PROVENANCE.md

记录：

local file
upstream file
upstream project
upstream URL
commit hash
copyright holder
license
modification description

如果没有复制第三方源码，也记录：

No third-party source files currently vendored.

====================
2.11 项目自身许可证

不要在未分析第三方依赖之前随意选许可证。

优先评估：

MIT
Apache-2.0
BSD-3-Clause

哪个更适合 ReverbScope。

在决定前考虑：

DSP 开源项目生态
商业使用
社区贡献
专利条款
第三方依赖兼容性

最终选择必须写入：

docs/LICENSE_DECISION.md

解释为什么选择这个许可证。

====================
三、v0.1 功能范围

第一版只建立可靠底座，不追求大量功能。

必须包含两个工作流。

A. Universal DAW Mode

ReverbScope：

生成标准 ESS Sweep WAV
用户将 Sweep 导入任意 DAW
DAW 通过声卡/监听音箱播放
测量麦克风录制返回信号
用户从 DAW 导出 recorded WAV
将 recorded WAV 导入 ReverbScope
ReverbScope 自动完成分析

尽可能自动识别 Sweep 的时间位置。

不要要求用户精确手工裁切。

B. Standalone Mode

ReverbScope 能够：

枚举音频输入设备
枚举音频输出设备
选择 Sample Rate
选择 Output
选择 Input
播放测试 Sweep
同时录制麦克风
保存原始录音
自动进入分析

Standalone Mode 与 Universal DAW Mode 必须最终调用同一个 Analysis Core。

====================
四、v0.1 声学分析功能

只实现以下核心内容。

ESS Sweep generation

生成 logarithmic exponential sine sweep。

至少支持：

44.1 kHz
48 kHz
88.2 kHz
96 kHz

默认：

48 kHz

建议默认 Sweep：

20 Hz – 20 kHz

提供：

duration
start frequency
end frequency
fade
level

参数。

Impulse Response

从原始 Sweep 和录制信号中通过 deconvolution 得到 Room Impulse Response。

必须：

正确处理时间对齐
保留原始数据
避免不必要的 destructive processing
对异常输入做错误检测

Frequency Response

从有效 IR 中生成频率响应数据。

允许合理 smoothing。

但：

原始曲线必须保留
smoothing 必须可配置
不得把平滑后的结果冒充原始测量

Reverberation analysis

至少设计支持：

EDT
RT20
RT30
estimated RT60

只有在数据动态范围满足条件时才计算对应指标。

数据不足时明确显示：

Insufficient decay range

而不是强行生成数字。

Background Noise

支持在录音文件中的安静区段分析：

RMS
spectral distribution
低频 hum 风险
50 Hz / 60 Hz 及其谐波

注意：

如果系统没有经过 SPL calibration，

不得把数字描述成真实 dB SPL。

只能使用：

dBFS

或者 relative measurement。

Low-frequency resonance

检测明显的低频峰值和长衰减区域。

第一版只做：

Potential resonance

不要未经充分验证就声称确定识别具体 room mode。

Early Reflections

根据 IR 分析直达声之后的明显早期反射。

输出：

delay
relative level

例如：

Strong reflection detected around 18 ms, approximately -9 dB relative to direct sound.

但需要考虑 direct sound detection 的可靠性。

====================
五、第一版不要做

暂时不要实现：

AI 自动混音
自动 EQ 修正
VST3
AU
AAX
Pro Tools SDK
Cubase SDK
云端服务
用户账户
登录
数据库
社交功能
复杂 3D 房间建模
自动计算吸音材料购买数量
伪科学的"房间评分"

尤其不要简单生成一个：

Room Score = 83/100

这样的数字。

录音环境没有足够证据时不能被压缩成伪精确评分。

====================
六、技术架构

优先评估：

Python 3.12+

核心候选：

NumPy
SciPy
sounddevice
soundfile
matplotlib
PySide6

可以研究：

pyroomacoustics

但不要因为某个库已经存在就让整个项目强依赖它。

如果只需要其中少量算法，应评估：

dependency cost
license
maintainability
cross-platform support
future packaging impact

任何第三方代码使用前必须完成 License Review。

====================
七、推荐项目结构

请先评估并优化类似结构，而不是机械照抄：

reverbscope/

src/
reverbscope/

core/
sweep/
deconvolution/
impulse/
acoustics/
noise/
reflections/
audio/
devices/
playback/
recording/
io/
wav/
session/
export/
models/
measurement.py
result.py
configuration.py
ui/
main_window/
measurement/
analysis/
utils/

tests/

unit/
integration/
fixtures/

docs/

examples/

scripts/

pyproject.toml
README.md
LICENSE
CONTRIBUTING.md
CHANGELOG.md

不要创建巨大 God Class。

DSP 算法必须尽可能保持 pure functions，以便测试。

====================
八、Measurement Session

项目从一开始就应建立统一 Measurement Session 数据模型。

一次测试应该能够记录：

project/session id
room name
measurement position
microphone name
microphone type
microphone calibration status
audio interface
input channel
output channel
loudspeaker
sample rate
bit depth
sweep settings
original sweep path
recorded file path
impulse response
analysis result
notes
timestamp

第一版可以保存 JSON。

以后再考虑其他格式。

Raw measurements 必须尽量可重复分析。

不要只保存最终图片。

====================
九、GUI 第一版

GUI 保持工程工具风格。

不要追求炫酷设计。

首页只需要：

New Measurement

两种模式：

Universal DAW Mode
Standalone Mode

Universal DAW Mode：

Step 1
Generate Test Signal

Step 2
Record Through Your DAW

Step 3
Import Recording

Step 4
Analyze

Results 页面包含：

Overview
Impulse Response
Frequency Response
Decay
Noise
Early Reflections

图表必须：

单位清楚
坐标清楚
可重复
不误导

====================
十、录音师导向

这个项目和传统声学工具最大的区别之一是：

不仅显示数据，还应该帮助录音师理解数据。

但是解释层必须和 DSP measurement 层分离。

例如 DSP 层返回：

early_reflection:
delay_ms = 18.4
relative_db = -8.7

Interpretation layer 才可以解释：

A relatively strong early reflection is present approximately 18 ms after the direct sound. For close vocal recording, try moving the microphone or performer farther from nearby hard surfaces and measure again.

以后允许加入：

Vocal
Voice-over
Acoustic Guitar
Drums
Room Mic
Choir

等 Recording Profiles。

但 v0.1 先只把接口设计好。

====================
十一、测试要求

这是 DSP 软件。

测试非常重要。

不要只测试程序"能不能运行"。

请建立：

synthetic impulse tests
known decay tests
generated sweep/deconvolution round-trip tests
noise tests
invalid file tests
stereo/mono handling tests
sample-rate tests

对于可以数学验证的算法：

必须使用已知输入和已知预期结果验证。

必要时创建 synthetic RIR。

不要依赖真实房间录音作为唯一测试数据。

====================
十二、安全原则

Standalone 测量涉及音箱播放。

默认 Sweep level 必须保守。

第一次测量前显示：

Start with your monitor/interface output at a low level.

不得突然满幅输出测试信号。

任何代码都不要：

自动修改系统音量
自动修改 DAW 设置
自动修改系统音频配置
安装未经说明的驱动

====================
十三、本轮 Cowork 的任务

这是第一次初始化。

不要马上把整个 v0.1 全部写完。

本轮按照下面顺序工作：

PHASE 1 — Research, License Audit & Architecture

先检查工作目录。

研究：

当前可用的成熟 Python DSP 实现
ESS measurement methodology
impulse response deconvolution
reverberation time measurement
third-party library licenses
reference repository licenses
relevant academic papers
relevant standards

对于发现的外部仓库：

先检查 License。

License 不明确的代码不得复制。

建立：

docs/ARCHITECTURE.md
docs/MEASUREMENT_METHODOLOGY.md
docs/THIRD_PARTY_REVIEW.md
docs/DEPENDENCIES.md
docs/CODE_PROVENANCE.md
docs/LICENSE_DECISION.md

明确所有核心技术选择。

PHASE 2 — Repository Foundation

建立：

Python project
src layout
packaging
configuration
logging
error model
basic data models
testing infrastructure
lint/type-check configuration

PHASE 3 — Minimal DSP Core

只实现一个可以验证的最小链路：

Generate ESS
↓
Load recorded WAV
↓
Align
↓
Deconvolve
↓
Generate IR
↓
Calculate basic decay
↓
Export result

核心 DSP 优先根据论文、公式和公开方法独立实现。

如需使用第三方实现：

先记录 License 与 provenance。

使用 synthetic test 自动证明 round-trip 工作正常。

PHASE 4 — Minimal GUI

只有 DSP Core 通过测试以后再建立最小 PySide6 GUI。

GUI 第一版只需要：

Generate Sweep
Import Recording
Analyze
View Results

不要为了 GUI 破坏 Core 架构。

PHASE 5 — Verification

完成后：

运行全部 tests
运行 lint
运行 type checks
检查 dependencies
检查 licenses
检查 provenance
检查 NOTICE requirements
检查 copyright attribution
检查未使用文件
检查 TODO
验证 macOS 基本运行

最后生成：

docs/STATUS.md

内容包含：

Implemented
Tested
Known limitations
Not implemented
Dependencies
License status
Third-party provenance
Known licensing risks
Next recommended milestone

====================
十四、工作方式

你具有执行权限。

不要只给我教程。

直接在工作目录中建立项目。

但：

在做重大架构决策前先充分检查现有代码、论文、依赖和许可证。

不要因为追求速度堆技术债。

不要因为一个 GitHub 项目"很好用"就直接复制它。

不要把"开源"理解成"可以随便拿"。

如果发现我上面的技术设想存在：

声学问题
DSP 问题
软件工程问题
跨平台问题
许可证问题
专利问题

不要盲目服从。

请指出问题并选择更可靠的实现。

不要虚构测试成功。

只有实际运行通过的测试才能写 PASS。

不要虚构 License。

如果无法确定某个依赖或仓库的许可证：

标记为 UNKNOWN / NEEDS REVIEW。

在许可证确认以前：

不要复制对应源码。

整个项目优先级：

正确性

法律与许可证清晰
可验证性
架构清晰
可维护性
跨 DAW
功能数量
UI 华丽程度

现在开始建立 ReverbScope 的可靠底座。

---

## 二、Git / GitHub 托管规则（第二条指令）

请把当前 ReverbScope 项目托管到我的 GitHub 仓库中。

要求：

如果当前还没有 Git 仓库，先初始化 Git。
检查并完善 .gitignore，不要提交：
* .venv
* Python cache
* build artifacts
* 临时测试文件
* 本地配置
* API keys
* tokens
* credentials
* 系统生成文件
检查当前项目中是否存在任何敏感信息，确认没有密钥、账号、访问令牌或私人路径被提交。
保留并提交：
* source code
* tests
* README
* LICENSE
* CONTRIBUTING
* docs
* pyproject.toml
* lock/config files that should be version controlled
创建清晰的初始 commit。
如果 GitHub 仓库还不存在，请创建一个新的仓库：
ReverbScope
默认先创建为 Private repository。
将当前代码 push 到 GitHub。
设置默认分支为 main。
不要 force push。
不要覆盖任何已有远端历史。
如果发现远端仓库已经有内容，先检查差异并安全合并，不要直接覆盖。
完成后告诉我：
repository URL
current branch
latest commit
是否 push 成功
有没有文件因为安全原因没有提交

以后每完成一个稳定开发阶段，优先创建清晰的 Git commit，再 push 到该仓库。

在我明确同意之前：

不要公开仓库
不要创建正式 Release
不要修改项目许可证
不要删除远端分支
