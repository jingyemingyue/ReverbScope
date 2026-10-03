# ReverbScope 与同类工具的比较

[English](COMPARISON.md) | **简体中文**

> 本文是 [COMPARISON.md](COMPARISON.md) 的简体中文翻译。两者不一致时，以英文版为准。

最后核对：2026-09-24。关于其他工具的信息均取自其官方网页、手册和代码仓库（见文末“来源”）。价格、版本和支持平台会变化，使用前请向厂商确认。“未见说明”表示我们在这些来源中没有找到该信息，不表示该功能不存在。欢迎通过 issue 或 pull request 指正。

## ReverbScope 面向谁

ReverbScope 面向录音师、学生和家庭录音者。他们对一个房间和一个话筒位置有三个问题：*这里能录音吗？这个位置有什么问题？移动话筒或演奏者之后有没有改善？* ReverbScope 负责测量、报告和比较，不校正监听系统，不模拟房间，也不调试扩声系统。

ReverbScope 目前是**预发布版（0.4.x）**。它的 DSP 在 Linux、macOS 和 Windows 上有合成测试覆盖，但还没有任何结果在真实硬件上测量并与参考仪器对照过（[STATUS.md](STATUS.md)、[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)）。下文的其他工具大多是成熟产品，已有多年实际使用经验。

## ReverbScope 的不同之处

下面有些做法在其他工具中已经存在：REW 会标出它认为不可靠的 RT60 数值；衰减没有高出噪声足够多时，Smaart 会从 T30 退回到 T20；双通道分析仪（Smaart、ARTA、Open Sound Meter）使用参考通道。ReverbScope 的特点在于把这些做法组合起来，专门用于录音位置，并且宁可不给数字，也不猜一个。

- **每个数字都有单位、算法来源和有效性标记。** 单位写在字段名里，每个指标的算法和文献出处都有文档说明。每个指标标记为 `valid`、`insufficient_decay_range`、`unreliable`、`outside_excitation_range` 或 `not_computed`。EDT、T20、T30 分别需要至少 20、35、45 dB 的衰减范围（ISO 3382 的噪声余量）。范围不够时，报告会写 *“Insufficient decay range”*（衰减范围不足），并给出实测范围。电平一律用 dBFS；dB SPL 需要校准，而 1.0 不提供校准。ReverbScope 有意不给单一的“房间评分”（[MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §3、§9；`src/reverbscope/models/result.py`）。
- **两种模式，一条分析流程。** 在通用 DAW 模式下，ReverbScope 生成扫频 WAV，你在任何 DAW 中播放并录音，再由 ReverbScope 分析导出的文件。ReverbScope 从不与 DAW 通信：没有 SDK，也没有插件。它能在未裁切的文件中任意位置找到扫频，所以不需要设置延迟；它能读取 Broadcast WAV、RF64、Wave64、AIFF、CAF 和 FLAC。在独立模式下，ReverbScope 自己通过音频接口播放和录音。两种模式都调用 `reverbscope.core.pipeline.analyze`（[user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md)）。
- **能解释 DAW 以错误速度播放的扫频。** 反卷积失败时，ReverbScope 会在录音中测出扫频速率（对扫频时间与对数频率的关系做 Theil–Sen 拟合），然后报告是采样率不匹配（“a file generated at 48000 Hz was played at 44100 Hz”），还是时间伸缩（Warp、Flex、Follow Tempo）。这只是诊断：ReverbScope 从不按测得的速度重新分析录音（MEASUREMENT_METHODOLOGY.md §2b）。
- **录音配置（profile）的建议明确标注为“解读”。** 建议来自录音配置，而不是 DSP。配置包括 generic（通用）、vocal（人声）、voiceover（配音/旁白）、acoustic_guitar（木吉他）、drums（鼓）、room_mic（房间话筒）和 choir（合唱），各有自己的阈值和措辞。报告会在 “Interpretation” 旁边印出配置名，所以没有人会把建议误当成与录音类型无关的结论（§8）。
- **摆位几何只给一支话筒测得出的内容。** 根据反射延迟，加上可选的卷尺测得的扬声器距离和话筒高度，ReverbScope 报告扬声器高度和上方表面的高度。它不给坐标，不给房间长度或宽度，也从不指明是哪面墙：一支全指向话筒在一个位置只能测到路径长度，测不到方向。如果两个到达声都能解释同一个数值，两者都会列出，不会挑选其一（§7a）。
- **可选的回送（loopback）补偿。** 音频接口输出的电回送会先经过检查：它必须表现为电脉冲。通过后，它用来从测量中除去接口自身的响应，并提供电气时间原点。如果该通道仍带有房间声音，ReverbScope 会拒绝它、说明原因，并在不补偿的情况下继续分析（§2a）。
- **会话比较，每个差值都有有效性。** 比较两个位置，回答“移动之后有没有改善？”。只有两边都有效时才给出衰减差值；噪声差值要求声明输入增益未变；仅凭一对测量，从不把任何变化称为“显著”（§11）。
- **英文和简体中文；Apache-2.0 许可，净室来源。** 解读结论、图形界面、命令行帮助和用户指南都已翻译（[user-guide/zh-CN.md](user-guide/zh-CN.md)）。核心诊断字符串有意保持英文（[ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) §5.6）。所有 DSP 都依据论文和标准编写，没有收录任何第三方源代码；设计阶段研究过的每个代码仓库都做过许可证审查（[CODE_PROVENANCE.md](CODE_PROVENANCE.md)、[THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md)）。

## 对比表

“经由 DAW”指由 DAW 或其他录音设备播放测试信号并录下话筒，再由该工具分析这些文件。对于校正类产品，这一栏写的是校正在哪里运行。

| 工具 | 许可 / 收费方式 | 平台 | 主要用途 | 经由 DAW / 其他录音设备 | 激励信号 / IR 方法 | 是否报告指标有效性 |
| --- | --- | --- | --- | --- | --- | --- |
| **ReverbScope** | Apache-2.0，免费 | Windows 10/11 x64；macOS 14+（arm64、x86_64）；Linux x86_64；Python 3.12+ wheel | 测量并解读录音位置 | 是：通用 DAW 模式（输出 WAV、读入 WAV）；另有独立模式 | 指数正弦扫频，逆滤波反卷积；可选回送；可导入 IR WAV（`analyze-ir`） | 是：每个指标和每个比较差值都有标记；无法支撑的数值不给出 |
| REW（Room EQ Wizard） | 专有免费软件；Pro 升级收费 | Windows、macOS、Linux | 测量与分析；EQ 滤波器设计；房间模拟器 | 是：离线测量。REW 扫频在别处播放并录音，再用 *Import Sweep Recordings* 载入（需要时间基准信号） | 对数扫频；步进正弦；噪声 RTA | RT60：显示回归系数；它认为不可靠的数值以橙色斜体显示；用 Lundeby 本底噪声估计标出数据不再有效的位置 |
| Open Sound Meter | 桌面版 GPL-3.0，随意付费；iPad 版在 App Store | macOS、Windows、Linux；iPadOS | 实时调试扩声系统 | 未见说明 | 双通道 FFT：RTA、幅度、相位、脉冲响应、相干、群延迟 | 相干；混响指标未见说明 |
| ARTA | 自 2024 年 12 月起为免费软件（2024 年 3 月停止销售） | Windows | IR、频率响应和频谱测量；ISO 3382 房间参数 | 自己驱动声卡；可导入 IR 和信号 WAV 文件；经由 DAW 播放未见说明 | 周期噪声、MLS、线性和对数扫频；单通道或双通道 | 衰减回归的相关系数 |
| Smaart（Rational Acoustics） | 商业软件，永久授权或年度订阅；只有 Smaart Suite 含 IR 模式 | Windows 10 64 位；macOS 10.14+ | 实时调试扩声系统；IR 模式含 RT60 和 STI | 需要实时输入；信号发生器可播放 WAV/AIFF 文件；可打开 WAV/AIFF 脉冲响应 | 双通道传递函数加逆 FFT，使用粉红噪声或 “pink sweep”（对数扫频）；对冲击声源可单通道录音 | 传递函数有相干；T30 终点未高出本底噪声 10 dB 时改用 T20；建议用户逐频带检查自动估计的“鞍点” |
| SoundID Reference（Sonarworks） | 商业软件，永久授权的多个版本 | macOS 11–15；Windows 10/11 | 扬声器和耳机校准（校正） | 校正以 DAW 插件或全系统方式运行；测量在其自带应用中进行 | 用测量话筒测房间与扬声器的频率响应；测试信号未见说明 | 未见说明（未见房间声学指标说明） |
| ARC X（IK Multimedia） | 商业软件；已注册的兼容 IK 硬件用户免费 | macOS、Windows | 监听的房间校正 | 校正以插件、ARC Studio 硬件或扬声器内置 DSP 运行；测量在其自带应用中进行 | 1、3、7 或 21 点测量（VRM）；测试信号未见说明 | 未见说明 |
| Dirac Live | 商业软件 | 电脑应用；兼容的 AV 功放和处理器 | 校正脉冲响应和频率响应（混合相位滤波器） | 校正在硬件或电脑音频中运行；测量在其自带应用中进行 | 在多个聆听位置测量脉冲响应；测试信号未见说明 | 未见说明 |
| HouseCurve | 免费应用，部分功能收费 | iOS、iPadOS | 测量并生成 EQ/FIR 滤波器 | 未见说明 | 正弦扫频；实时粉红噪声 | 对扫频测量做“自动验证” |
| AURORA（A. Farina） | “发布（不出售，也不授权）” | Adobe Audition 1.0–3.0 插件；另有 Audacity 移植版 | IR 测量、ISO 3382 参数、可听化 | 是：在音频编辑器内运行 | 对数正弦扫频 | 未见说明 |
| pyroomacoustics | MIT，免费 | Python（pip） | 房间模拟（镜像源、射线追踪）；阵列信号处理 | 不适用；`experimental.measure_ir` 通过 sounddevice 播放和录音 | 模拟 RIR；实验性的指数/线性扫频加反卷积；`measure_rt60`（Schroeder） | 未见说明（`energy_thres` 可限制在噪声尾部上的拟合） |
| python-acoustics | BSD-3-Clause；2024 年 2 月已归档 | Python | 通用声学库（分析） | 不适用 | 分析给定的信号（例如由 IR 求 T60） | 未见说明 |
| pyrato（pyfar） | MIT，免费 | Python | 从实测或模拟的 RIR 计算房间声学参数 | 不适用（仅分析） | 带噪声处理的能量衰减曲线（Chu 噪声扣除法、Lundeby） | 未见说明 |
| ITA-Toolbox（亚琛工业大学） | 开源（据本项目审查为 BSD-4-Clause） | MATLAB | 研究工具箱：测量、信号处理、ISO 3382 房间声学 | 使用自己的播放和录音 | 噪声、扫频或 MLS 传递函数 | 符合 ISO 3382 的噪声处理方法；逐指标标记未见说明 |

## 什么情况下其他工具更合适

- **设计 EQ 和房间校正滤波器、瀑布图、房间模拟。** REW 能自动找出响应峰值，为多种硬件和软件均衡器分配并优化 EQ 滤波器，并绘制瀑布图和声谱图；它还有房间模拟器。ReverbScope 不设计任何滤波器。
- **校正监听系统。** SoundID Reference、ARC X 和 Dirac Live 的测量是为了校正；HouseCurve 为高保真和家庭系统生成滤波器。ReverbScope 只测量。如果要用 ReverbScope 测量校正后的系统，请有意把校正保留在回放链路中（[user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md) 第 3 条）。
- **现场扩声和实时传递函数。** Smaart 和 Open Sound Meter 可以用节目素材实时显示双通道 FFT 结果和相干。ReverbScope 是离线工作的，一次一个扫频。
- **STI、强度和 ISO 3382 的其余参数。** REW Pro（STI）、Smaart Suite（STI、清晰度）、ARTA 和 AURORA 报告语言传输指数、声音强度或侧向能量。ReverbScope 报告 EDT、T20、T30、估计 RT60，以及单点能量比 C50、C80、D50 和重心时间（方法文档 §3b）。它不报告 STI，也不报告强度 G，这些比值也不是房间评分。
- **校准后的 SPL 或经认证的测量。** ReverbScope 只报告 dBFS；它的频带滤波器未经 IEC 61260 1 级认证，一个声源加一个话筒位置也达不到 ISO 3382-2 的简易（survey）等级（方法文档 §3）。ARTA 配合校准话筒可作为虚拟 IEC 1 级声级计，Smaart 也有 SPL 模式。
- **房间模拟和研究脚本。** pyroomacoustics 用于模拟房间；pyrato 和 ITA-Toolbox 可在 Python 或 MATLAB 中计算房间参数。
- **今天就需要经过实地验证的结果。** ReverbScope 还没有硬件验证。在 0.5.0 之前，请把它的数字视为未经验证。

## ReverbScope 有意不做的事

摘自 [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §9 和 [ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) §3.3：

- 不给房间评分。
- 不做自动 EQ，也不做房间校正；校正滤波器设计领域专利密集（方法文档 §10）。
- 没有校准就不给 dB SPL；1.0 中所有电平都是 dBFS。
- 不识别房间模态，只报告*可能的*低频共振（方法文档 §7）。
- 不承载插件，1.0 也不提供 VST3/AU/AAX 插件。
- 除垂直方向外不给任何房间几何：不给坐标，不给房间长度或宽度，不指明墙面。要从回声推出房间的完整形状，需要话筒阵列或多个位置；两个位置恰好是定解，因此将来若支持多位置，必须再加一个冗余的第三个位置。
- 空间平均只平均 T 值，从不平均衰减曲线。
- 不估计独立播放设备与录音设备之间的时钟漂移，也不采用自动双扫频方案（两者都有有效专利）。
- 不使用云服务，没有账户，没有遥测。

## 来源

访问日期 2026-09-24。关于 ReverbScope 的内容取自本仓库：上文链接的文件，以及其中引用的许可证审查记录 [research/reference_repos.md](research/reference_repos.md)。

- REW：[主页](https://www.roomeqwizard.com/)、[功能](https://www.roomeqwizard.com/features.html)、[离线测量](https://www.roomeqwizard.com/help/help_en-GB/html/offlinemeasurements.html)、[RT60 图](https://www.roomeqwizard.com/help/help_en-GB/html/graph_rt60.html)、[RT60 衰减图](https://www.roomeqwizard.com/help/help_en-GB/html/graph_rt60decay.html)、[EULA](https://www.roomeqwizard.com/eula.html)
- Open Sound Meter：[主页](https://opensoundmeter.com/)、[代码仓库（GPL-3.0）](https://github.com/psmokotnin/osm)
- ARTA：[主页](https://www.artalabs.hr/)、[用户手册](https://artalabs.hr/download/ARTA-user-manual.pdf)
- Smaart：[版本说明](https://support.rationalacoustics.com/support/solutions/articles/150000188536-which-edition-of-smaart-is-right-for-me-)、[价格](https://www.rationalacoustics.com/pages/smaart-v9-pricing)、[系统要求](https://www.rationalacoustics.com/pages/smaart-v9-minimum-system-requirements)、[Smaart v8 用户指南](https://downloads.rationalacoustics.com/documentation/smaart-v8/Smaart-v8-User-Guide.pdf)
- SoundID Reference：[产品页](https://www.sonarworks.com/soundid-reference)、[价格](https://www.sonarworks.com/soundid-reference/pricing)
- ARC X：[产品页](https://www.ikmultimedia.com/products/arcx/)
- Dirac Live：[房间校正](https://www.dirac.com/products/room-correction)、[维基百科：Digital room correction](https://en.wikipedia.org/wiki/Digital_room_correction)
- HouseCurve：[主页](https://housecurve.com/)
- AURORA：[主页](https://www.aurora-plugins.com/index.htm)
- pyroomacoustics：[代码仓库](https://github.com/LCAV/pyroomacoustics)、[measure_ir](https://pyroomacoustics.readthedocs.io/en/pypi-release/pyroomacoustics.experimental.measure_ir.html)、[measure_rt60](https://pyroomacoustics.readthedocs.io/en/pypi-release/pyroomacoustics.experimental.rt60.html)
- python-acoustics：[代码仓库](https://github.com/python-acoustics/python-acoustics)
- pyrato：[代码仓库](https://github.com/pyfar/pyrato)、[文档](https://pyrato.readthedocs.io/en/latest/modules/pyrato.html)
- ITA-Toolbox：[主页](https://www.ita-toolbox.org/)、[测量与房间声学论文](https://www.ita-toolbox.org/publications/ITA-Toolbox_paper4.pdf)
