# ReverbScope 用户指南

[English](en.md) | **简体中文**

ReverbScope 用来测量录音房间，让你听清房间对近距离拾音的声源做了什么。它不给房间打分，也不做校正。

本页是中文指南，英文原文见 [en.md](en.md)；两者不一致时以英文版为准。

## 安装

从项目的 [Releases 页面](https://github.com/jingyemingyue/ReverbScope/releases)下载。各系统的分步说明、更新、卸载和故障排查见 [INSTALLATION.zh-CN.md](../INSTALLATION.zh-CN.md)，本节是简要版。每个 Release 都附有一个 `SHA256SUMS` 文件，请与下载文件的校验值比对（macOS / Linux：`shasum -a 256 <file>`；PowerShell：`Get-FileHash <file>`）。

ReverbScope 有两个版本。**桌面版**就是本指南介绍的应用程序，同时包含命令行；**终端版**只有命令行（没有窗口和图表），
适合脚本、服务器和没有图形桌面的电脑。

| 系统 | 桌面版 | 启动 ReverbScope |
| --- | --- | --- |
| Windows 10/11 x64 | `ReverbScope-Desktop-Windows-x64-Setup.exe`（安装程序）或 `ReverbScope-Desktop-Windows-x64.zip` | 开始菜单 → ReverbScope，或运行 zip 中的 `reverbscope-gui.exe` |
| macOS 14+，Apple 芯片 | `ReverbScope-Desktop-macOS-arm64.dmg` | 把 ReverbScope 拖进“应用程序”文件夹，然后打开 |
| macOS 14+，Intel | `ReverbScope-Desktop-macOS-x86_64.dmg` | 把 ReverbScope 拖进“应用程序”文件夹，然后打开 |
| Linux x86_64 | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | `tar xzf ReverbScope-Desktop-Linux-x86_64.tar.gz && reverbscope/reverbscope-gui` |

| 系统 | 终端版 | 启动 ReverbScope |
| --- | --- | --- |
| Windows 10/11 x64 | `ReverbScope-Terminal-Windows-x64.zip` | 解压后双击 `ReverbScope Terminal.cmd`，输入 `reverbscope.exe demo` |
| macOS 14+，Apple 芯片 | `ReverbScope-Terminal-macOS-arm64.tar.gz` | 用 `tar xzf` 解压，然后运行 `reverbscope-terminal/reverbscope demo` |
| macOS 14+，Intel | `ReverbScope-Terminal-macOS-x86_64.tar.gz` | 用 `tar xzf` 解压，然后运行 `reverbscope-terminal/reverbscope demo` |
| Linux x86_64 | `ReverbScope-Terminal-Linux-x86_64.tar.gz` | 用 `tar xzf` 解压，然后运行 `reverbscope-terminal/reverbscope demo` |

Windows 和 Linux 的桌面版安装包含两个程序：桌面程序 `reverbscope-gui` 和命令行工具 `reverbscope`（在终端运行 `reverbscope --help`）。在 macOS 上，应用的可执行文件带参数运行时就是命令行工具：`/Applications/ReverbScope.app/Contents/MacOS/ReverbScope --help`。

在维护者取得签名证书之前，**这些安装包都没有用于分发的签名**（macOS 应用只有临时签名（ad hoc），未经公证；Windows 文件没有 Authenticode 签名），因此首次打开时操作系统会发出警告：

* **macOS：** 先打开一次应用；macOS 提示无法验证时选“完成”，然后进入“系统设置 → 隐私与安全性”，点“仍要打开”（该按钮在第一次尝试打开之后才会出现）并确认。从 macOS 15 Sequoia 起，右键 → “打开”不再能绕过这一检查；在 macOS 14 上仍然可用（[Apple](https://developer.apple.com/news/?id=saqachfa)）。系统询问时请允许麦克风访问（安装包的 Info.plist 中声明了 `NSMicrophoneUsageDescription`）。打包的 NumPy 和 SciPy 需要 macOS 14 或更新版本；DMG 只在 macOS 15（Intel）和 macOS 26（Apple 芯片）的 CI 运行器上构建和启动过。
* **Windows：** SmartScreen 可能发出警告，请选“更多信息”→“仍要运行”。安装程序只为当前用户安装，不需要管理员权限；可在“设置 → 应用”中卸载。
* **Linux：** tar 包需要系统自带的 PortAudio、OpenGL/EGL 和 XCB 库（Debian / Ubuntu：`sudo apt install libportaudio2 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0`）；图表中要显示中文，还需要中文字体，例如 `fonts-noto-cjk`。`packaging/linux/reverbscope.desktop` 是一个可以按需修改的桌面启动项。

**用 Python 安装。** ReverbScope 还没有发布到 PyPI。使用 Python 3.12 或更新版本，把 Release 附带的 wheel 安装到虚拟环境中：

```bash
python3 -m venv reverbscope-env
reverbscope-env/bin/pip install "./reverbscope-<version>-py3-none-any.whl[gui]"
reverbscope-env/bin/reverbscope gui
```

只需要命令行和 Python API 时去掉 `[gui]`。`pip install -e ".[gui]"` 是从克隆的源码进行的开发者安装。

“关于”对话框和 `THIRD_PARTY_LICENSES/` 列出了 Qt、libsndfile 以及其他随包组件的许可证。

## 先试一试：演示

`reverbscope demo` 不需要音频接口和话筒，就能演示完整的工作流程。它会写出扫频，模拟一个虚构房间里
两个位置（一个靠近桌面和侧墙，一个向后移开）的话筒会录到什么，用与真实测量相同的代码分析这两个位置，
并对比它们。输出的导览最后会给出查看完整报告、对比结果、打开桌面应用以及开始你自己第一次测量的命令。

演示中的任何内容都不是测量结果：终端第一行就会说明这一点；每个保存的会话的模式都是
`synthetic_demo`，并附有说明它是模拟数据的备注；演示也绝不会覆盖不是它自己写出的文件夹。
用 `reverbscope demo --out <文件夹>` 可以指定文件的位置。演示给会话起的房间、位置和话筒名称，
用运行演示时的界面语言写入；打开、列出或生成报告时，则按当前界面语言显示。

桌面应用本身没有演示模式。它像打开任何已保存的会话一样打开演示写出的会话（“文件 → 打开会话…”，或 `reverbscope demo` 打印出的那些文件夹），并在测量列表、“属性与诊断”面板和窗口标题中把它们标为“合成数据”。

## 通用 DAW 模式

1. `reverbscope sweep --sample-rate <project rate> --out sweep.wav`（或在桌面应用中打开“测量 → 导入 DAW 录音…”，对话框的测试信号部分会按你选择的采样率——也就是工程采样率——写出同样的 WAV 和配套文件）。把 `.reverbscope-sweep.json` 配套文件和 WAV 放在一起。
2. 把 WAV 导入 DAW 的一条新轨道，关闭时间伸缩（Warp、Flex、Follow Tempo），信号通路上不要有插件。把它路由到一只扬声器。
3. 在第二条轨道上接入测量话筒并开启录音待命，关闭输入监听，在扫频播放的同时录音。完整导出录音轨，不要裁切，也不要标准化。
4. 可选回送（loopback）：导出双声道文件（话筒 + 电回送），并使用 `--channel 0 --loopback-channel 1`。
5. `reverbscope analyze --recording take.wav --sweep sweep.wav --out session/`，或在桌面应用的“导入 DAW 录音”对话框中用“选择录音…”和“选择参考扫频…”选择这些文件（在同一对话框里生成的测试信号默认就是参考信号），选好话筒声道和回送声道、录音配置和元数据，然后点“分析”：对话框关闭，状态行显示分析进度，结果加入测量列表。DAW 的分步说明折叠在对话框里。

**Pro Tools、Logic Pro / GarageBand、Cubase / Nuendo、Fender Studio Pro（原 PreSonus Studio One）、Ableton Live、REAPER、FL Studio、Bitwig Studio、Digital Performer 和 Audacity 的分步说明，以及报告中各条提示在 DAW 里对应的原因，见 [daw-setup.zh-CN.md](daw-setup.zh-CN.md)。**

## 独立模式与回送线

`reverbscope devices` 列出音频接口。`reverbscope measure --out session/` 播放扫频并录音。`--input-channels 1,2 --loopback-channel 2` 在输入 2 上录制电回送。

这次测量的 `sweep.wav` 和 `recording.wav` 只会连同描述它们的会话一起写入该文件夹：中途停止或被拒绝的测量不会改动文件夹。对已有会话的文件夹再次测量会替换该会话。文件夹里已有扫频或录音文件、却没有会话时（例如你用 `reverbscope sweep --out folder/sweep.wav` 生成的扫频），在播放任何声音之前就会被拒绝。

先把监听电平调低。高于 −12 dBFS 的电平每次都需要 `--acknowledge-level` 确认；该确认从不保存。

在桌面应用中，“测量 → 测量…”（Ctrl+M）打开独立模式对话框：音频系统和设备（推荐项带星标）、声道、采样率及设备采样率检查、测试信号（带播放电平上限及其确认）、录音配置、房间 / 位置 / 话筒，以及可选的卷尺测量和侧视示意图。点“运行”开始测量：对话框关闭，状态行显示真实进度，“停止”（Esc）始终在屏幕上；测量完成后，无论你在此期间选中了什么，结果都作为一条新条目加入测量列表。设备检查、“两个独立时钟”的询问和声道校验都在播放任何声音之前进行，与命令行相同。这次测量在“文件 → 保存会话…”写入之前只存在于内存中；关闭它或关闭窗口时会先询问（“保存会话…” / “放弃” / “取消”）。在“停止”之后或窗口关闭之后才到达的结果会被丢弃。

`reverbscope --backend fake measure` 在合成房间上运行同一流程；桌面应用的自动化测试用 `REVERBSCOPE_AUDIO_BACKEND=fake` 做同样的事。两者都不会向扬声器发送任何信号，这样得到的会话会标为“合成数据”。桌面应用没有演示入口。

### 各平台注意事项

`reverbscope devices` 在“主机 API”一列显示每个设备所属的音频系统；桌面应用把设备显示为 `[序号] 名称 (主机 API)`。

* **Windows。** 每个音频接口会按每种主机 API 各列一次。优先选主机 API 为 Windows WASAPI（或 Windows WDM-KS）的条目；避免 MME 和 Windows DirectSound，它们要经过 Windows 混音器。共享模式下 WASAPI 只能以设备的共享模式格式运行（[Microsoft：Device formats](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats)）：请在“声音”控制面板中把它设为测量采样率（控制面板 ▸ 硬件和声音 ▸ 声音 ▸ 该设备 ▸ 属性 ▸ 高级 ▸ *默认格式*），并把*音频增强*设为关闭（设置 ▸ 声音 ▸ 该设备）（[Microsoft 支持](https://support.microsoft.com/en-us/windows/fix-sound-or-audio-problems-in-windows-73025246-b61c-40fb-671a-2535c7cd56c8)）。允许桌面应用使用麦克风（设置 ▸ 隐私和安全性 ▸ 麦克风）。安装包不含 ASIO 支持（ASIO DLL 用 Steinberg 的专有 SDK 构建，已被移除，见 DEPENDENCIES.md §3）；只能通过 ASIO 工作的音频接口请用通用 DAW 模式测量。
* **macOS。** Core Audio。在“系统设置 ▸ 隐私与安全性 ▸ 麦克风”中允许 ReverbScope；没有该权限时录音是静音，ReverbScope 会报告 *“recording is silent”*。在“音频 MIDI 设置”中设定音频接口的采样率；输入和输出是不同设备时，可在那里把它们合成一个聚合设备。
* **Linux。** 通过系统的 PortAudio（`libportaudio2`）使用 ALSA。`hw:` 设备使用音频接口自身支持的采样率；`pipewire`、`pulse` 或 `default` 经过声音服务器，可能被重采样：ReverbScope 在测量前会把设备采样率显示在请求的采样率旁边。你的用户可能需要加入 `audio` 组。

## 读懂结果

每个指标都有有效性标记。`insufficient_decay_range`（衰减范围不足）表示数值被扣下不报，而不是等于零。没有单一总分。录音配置可能在宽带 C50 或 C80 不适合该类录音时给出一条提示；阈值是该配置的工程选择，不是评分。

**录音配置。**配置是指房间被用来判断的录音类型：人声、配音、原声吉他、鼓、房间话筒、合唱，或通用。每个配置对衰减、强早期反射、清晰度（C50 或 C80；鼓既不判断清晰度也不判断本底噪声）和低频都有自己的阈值。测量之前，测量对话框中配置选择框旁的“它关注什么？”按钮会说明所选配置关注什么、不判断什么，并给出具体数字；“属性与诊断”面板的“测量属性”标签页注明一次测量是在哪个配置下解读的；`reverbscope profiles` 列出所有配置，`reverbscope profiles vocal` 说明其中一个（`--format json` 输出数字）。这些阈值是工程取舍，见 [MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §8，从不是评分。

**测量健康**就是“属性与诊断”面板的“测量质量”标签页（点工具栏上的质量状态即可打开），也是文本报告中紧接“概览”之后的一节。它列出分析对这次录音本身所做的检查（参考信号、扫频、播放速度、直达声、电平、失真、采样丢失、衰减范围、本底噪声、录音长度，以及参与了测量时的回送和音频设备），每项为*良好*、*警告*、*无效*或*未知*，并给出原因、受影响的指标和下一步该做什么。*无效*表示某个数字不可信（录音削波、扫频播放速度不对）；*未知*表示无法进行该项检查（导入的脉冲响应）。扫频播放速度不对时，会列出各 DAW 设置采样率或关闭时间伸缩的位置，与[用 DAW 测量](daw-setup.zh-CN.md)中的步骤一致；分析无法完成时，这些步骤也会显示在错误信息之下。最差的一项决定整体状态；没有总分。

核心诊断（`warnings`、`notes`、`reason`）在 `result.json` 中保持英文，便于跨语言对照问题报告。界面和文本报告按界面语言显示它们。

窗口一打开就是工作台。菜单栏有“文件”“测量”“项目”“视图”“帮助”（开发者版还有“开发者”）；其下是一条紧凑的工具栏：测量、导入 DAW 录音、打开会话、项目、保存，然后是基线、单图 / 双图、所选测量的质量状态，以及“属性与诊断”面板的开关。中间的图表区显示上下排列的一张或两张图表（默认上面是频率响应，下面是衰减）。右侧的“测量”停靠面板列出每一个已打开的测量，按位置分组；每一行有该测量的颜色块、名称、显示复选框、质量状态和角色标记（基线、合成数据、未保存）。“属性与诊断”面板在需要时打开在底部（工具栏按钮、F10、双击列表行或点击质量状态），有“测量质量”“诊断”“测量属性”“数据表”“对比”“报告”六个标签页。底部的状态行显示真实的录音进度，录音期间“停止”始终在屏幕上。没有打开任何测量时，图表显示“未载入测量。”，工具栏提供测量、导入和打开项目。

这里管理的是测量，而不是切换页面：你打开的每个会话、导入的每个录音、完成的每次测量都加入列表，新的从不替换旧的。选中一行会显示该测量的属性和诊断，并把它的曲线加粗画在最上层；复选框可以隐藏或显示它的曲线而不关闭它；“文件 → 关闭测量”（Ctrl+W）把它移除。“设为基线”（工具栏、列表面板或 Ctrl+B）把一个测量标为基线，随后你选中的另一个就是候选（见[对比两个位置](#对比两个位置)）。窗口会记住大小、停靠面板、图表类型、图表数量和两张图表之间的分割；“视图 → 恢复默认布局”恢复默认布局，“视图 → 测量列表”（F9）和“视图 → 属性与诊断”（F10）隐藏或显示两个面板；在 1280×800 下图表区至少占宽度的 70 %（窗口最小 960×640）。

工作台图表用各自的颜色画出每个显示中的测量，颜色与列表中相同，选中的那条更粗并画在最上层。每个图表面板有一行控制条：图表类型、范围（所有显示的测量 / 仅选中 / 基线与选中）、该类型的选项（频率响应的“原始曲线”、衰减的“频带”）、“差异”、“复位缩放”、光标读数和“导出”（图表另存为 PNG…、曲线另存为 CSV…）。鼠标滚轮缩放，拖动平移，双击复位；“视图 → 联动缩放”只联动坐标轴相同的面板（频率 Hz、时间 s、时间 ms），从不跨轴联动。每条坐标轴都标明单位，包括 dBFS 和相对 dB。隐藏的第二张图表在显示之前不会重绘。

| 图表 | 显示内容 |
| --- | --- |
| 频率响应 | 每个显示中的测量的平滑响应，需要时加上原始曲线，以及所选测量的共振候选（在面板中选中后在曲线上标出）；设了基线后，“差异”在两条响应曲线下方以同一刻度画出候选 − 基线。 |
| 衰减 | 每个显示中的测量的宽带 Schroeder 曲线（Lundeby 截断），需要时加上各倍频程频带；在“数据表”标签页中选中一个频带会高亮其曲线；设了基线后，“差异”把基线和候选的宽带衰减画在一起。 |
| 噪声 | 每个显示中的测量的安静段频谱，附 RMS 电平（dBFS，未校准）和所选测量的哼声谐波。 |
| 脉冲响应 | 只画所选测量的脉冲响应。 |
| 早期反射 | 只画所选测量的 ETC 峰值，把直达声、每个候选、阈值和分析窗口放在同一条时间轴上；高亮的候选是面板中选中的那个。 |
| 摆位几何 | 只画所选测量的侧视图与其下的反射时间线（见[摆位](#摆位)）。 |

“属性与诊断”面板解释所选的测量。“测量质量”是整体状态、摘要和各项检查，附原因、受影响的指标和修正办法；“诊断”列出录音配置给出的解读，最严重的在前，附证据，双击（或“在图表中显示”）打开某一行背后的图表、频带或反射；“测量属性”是房间、位置、话筒、模式、配置、采样率、扫频、声道、保存路径和合成数据标记；“数据表”是各指标表格（衰减、能量、噪声频带、反射、共振、摆位长度和候选），每一行都链接到对应图表；“报告”是与 `reverbscope analyze` 输出相同的文本报告（警告列在末尾），带“复制报告”。标题都是功能性的；有效性、缺失数据和“不可比较”的原因始终可见。

“文件 → 导出”可以把所选测量的 CSV 表格写入一个文件夹（“CSV 表格…”，与 `reverbscope export` 相同的文件）、把你最后点击的图表保存为 PNG（“当前图表另存为 PNG…”）、复制文本报告（“复制报告”），或写出基线与候选的对比（“保存 comparison.json…”）；失败时会说明原因。

## 摆位

“摆位几何”图表显示所选测量的侧视图与其下的反射时间线。侧视图中，你实测的话筒高度和扬声器距离为实线；反射所允许的量（扬声器高度、水平间距、两个设备上方的平面，各自带输入不确定度和模型保留的每一个候选值）为虚线；没有输入的部分用点线画出示例长度；不画墙面，也不画房间轮廓。其下的反射时间线把直达声、每个候选、阈值和分析窗口放在同一条时间轴上。“属性与诊断”面板的“数据表”标签页列出解出的长度（“摆位长度”）和候选（“摆位候选”），附数值、有效性和被排除的原因；选中一行会在图表中高亮它。没有卷尺实测的扬声器距离时，ReverbScope 只报告每个到达声的多余路径，并指出该在测量对话框中填写哪个字段。它从不指明墙面，也不给出房间长度或宽度。

请在“测量”或“导入 DAW 录音”对话框的“卷尺测量”部分（带侧视示意图）、点击“运行”或“分析”之前填入卷尺数值，或在命令行中使用 `--speaker-distance` / `--mic-height` / `--temperature`。

## 对比两个位置

`reverbscope compare baseline/ candidate/ --same-input-gain`；在桌面应用中则是：打开两个测量，选中作为参照的那个并点“设为基线”（工具栏、列表面板或 Ctrl+B），再选中另一个，它就是候选；“属性与诊断”面板的“对比”标签页显示判定和各项差值，“输入增益未变”仍然是你在那里勾选的条件。只有两侧都是 VALID 时，衰减差值才是 VALID。噪声差值需要明确声明“输入增益未变”。任何变化都不会被称为显著；ISO 3382-1 给出的 T 的刚可察觉差只作为参考背景引用。

**判定。**在候选会话的录音配置下，对比会对混响、清晰度、早期反射、本底噪声和低频分别给出：*有意义的改善*、*有意义的退化*、*大概率无关紧要*、*不可比较*，或*证据不足*，并每次说明原因（“对比”标签页的标题行；报告中紧接“概览”之后的一节；`--format json` 中的 `verdict`）。判定依据配置的阈值（人声棚不在乎 0.30 s 变成 0.22 s；房间话筒会把变得过干的房间判为退化）、刚可察觉差，以及两次测量都在手时的测量健康；它从不根据一对位置就称某个变化“显著”（[MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §11a）。

“对比”标签页在“反射”和“共振”两张表格中列出配对的早期反射（延时相差 ±0.5 ms 以内）和低频共振（相差 1/6 倍频程以内，并带有 decay-distinguishable 标志）。低频共振只在两次测量都搜索过的范围内比较：在另一次测量从未搜索的频率（例如其扫频起点更高）发现的共振既不算消失也不算新出现；若有一次测量根本没有搜索，低频一栏显示“未比较”（报告中如此，“共振”表格下方也有同样的说明；两次测量的直达声并非都可信时，“反射”表格同样给出说明）。图表的“差异”视图对频率响应画出候选 − 基线，对衰减画出两条宽带衰减曲线。“文件 → 导出 → 保存 comparison.json…”（或 `reverbscope compare … --out comparison.json`）只写入数值；`reverbscope show comparison.json` 会再次打印报告并**重新推导**解读（解读从不存入该文件）。

## 项目、位置与总览

项目文件夹包含 `project.json` 和普通的会话文件夹；该文件记录每个会话是在哪个位置测的。用 `reverbscope project init --out room/ --name Booth` 新建（或“项目 → 新建项目…”；对普通文件夹用“打开项目…”，它会提议建成项目），再把会话归入位置：`reverbscope project add room/ session/ --position desk`（“项目 → 把已保存的会话加入项目…”）。对已有 `project.json` 的文件夹再次运行 `project init` 会被拒绝；加 `--force` 则重新开始这个项目，原有的位置不再保留。在桌面应用中，“打开项目…”（Ctrl+Shift+O）把项目的每个会话按位置分组列进“测量”面板并一起画出；项目名称会出现在窗口标题中。

**测量多个位置。**“项目 → 测量新位置…”打开测量对话框，房间填的是项目名称，位置填的是下一个空闲的标签（A、B……；想改成桌前、墙角等也可以）；扬声器、它的电平和输入增益保持不变，只移动话筒。随后“保存会话…”会把这次测量保存到项目里、以位置命名的文件夹中（`B-1`、`B-2`……），并在面板中记入该位置。同一位置测两次可以看出测量是否可重复：总览会说明两次是否在 T 的 5 % 刚可察觉差之内一致，不一致时也会直说。

**总览**（`reverbscope project overview room/`；桌面应用中是“项目 → 项目总览…”，同样的文本，带“复制总览”）在一个录音配置下（默认为最新一次测量自身的配置，或 `--profile`）读取每次测量：测量健康、RT60、清晰度、本底噪声和最强早期反射，以及它的*契合度*：配置对它没有警告则为*契合*，有警告则列出主题，测量无效或没有有效（VALID）混响时间则为*无法判断*。每个位置由其最健康、最新的一次测量代表；第一个位置之后的每个位置都带有其测量相对第一个位置的判定（与“对比”标签页相同的判定，并计入两次测量的健康）。随后是空间平均和 ISO 3382-2 等级，以及各位置 RT60 在房间内的差异；“下一步”说明接下来该测什么：为达到下一等级再测一个话筒位置（或第二个扬声器位置）、重复测量一次、重新测量某个位置、哪些位置契合。总览不为位置排名：两个都契合的位置之间，请根据判定和录音的需要来选。`--format json` 输出整个总览；`project.json` 除位置外不存储任何内容（[MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §13）。

`reverbscope project average room/` 只平均有效（VALID）的 T 值，从不平均衰减曲线，并注明测量位置数达到的 ISO 3382-2 等级。RT60 一列是各会话自身 RT60（优先 T30，否则 T20）的平均值。`n` 是该行参与平均的会话数；参与会话较少的数值会附上自己的会话数，例如 `0.91 s (1)`。

## 导出与语言

`reverbscope export session/ --format csv --out curves/` 导出每一条曲线。把另一个会话导出到同一文件夹时，该会话没有的曲线文件会被删除（`--no-curves` 会话没有任何曲线），因此文件夹里不会混有两个会话的数据。

ReverbScope 跟随系统语言：Mac 上是首选语言（“系统设置 → 通用 → 语言与地区”；“终端”、iTerm 和 VS Code 不管首选语言是什么都会设置 `LANG=en_US.UTF-8`，所以 `LANG` 排在首选语言之后），Windows 上是显示语言，Linux 上是 `LANGUAGE`、`LC_ALL`、`LC_MESSAGES` 和 `LANG`。和其他程序一样，`LC_ALL=C`（或 `LC_MESSAGES=C`）在任何系统上都给出英文，例如提交错误报告时运行 `LC_ALL=C reverbscope show session/`。想不管系统怎么设置都固定使用一种语言，保存一次即可：

```bash
reverbscope config language zh_CN   # 中文
reverbscope config language en      # English
reverbscope config language auto    # 改回跟随系统
```

`reverbscope config language` 显示当前使用的语言以及原因。桌面版的“文件 → 设置… → 语言”写入的是同一个设置。`--lang zh_CN` 只对一条命令指定语言，`REVERBSCOPE_LANG` 对一个终端会话指定语言；优先顺序是 `--lang`、已保存的设置、`REVERBSCOPE_LANG`、系统语言。主屏幕（直接运行 `reverbscope`）和 `reverbscope --help` 的最后一行用另一种语言写出切换到该语言的命令。

中文界面会翻译解读、文本报告的标签、图形界面和全部命令行帮助（`reverbscope --help` 及每个子命令，包括占位符和 argparse 自己的提示）。单位不翻译；数字保持 ASCII。诊断说明和警告在 `result.json` 中以英文保存，显示时翻译。

`reverbscope config` 列出桌面版保存的其他设置，并可以在命令行里修改它们，终端版也一样：`profile`（默认录音配置）、`backend`（`portaudio` 或 `fake`）、`output-folder`、`copy-recording` 和 `developer-tools`（`on` 或 `off`），以及 `theme`（`system`、`light` 或 `dark`，只影响桌面版）。例如 `reverbscope config profile vocal`；`auto` 把一项设置恢复为默认值，`reverbscope --format json config` 以 JSON 输出所有设置。

在终端里，命令行使用颜色和 ✓ ! × 符号；输出重定向到文件或其他程序时只写纯文本。`--color never` 或环境变量 `NO_COLOR` 关闭颜色，`--color always` 在管道中也保留颜色。

**带边框的报告。**在至少 48 列宽的终端里，报告标题放在方框中，小节标题嵌在横线里，表格带边框；状态行、命令和路径从不加框，中文按两列宽度计算，所以每个边框都对齐。输出到管道或文件时总是纯横线版式，`--format json` 不受影响。`--style plain` 或 `--style boxed` 决定一次命令的样式，`reverbscope config style plain|boxed|auto` 长期生效，环境变量 `REVERBSCOPE_CLI_STYLE` 对一个 shell 生效。若终端字体把方框字符画成两列宽，请选 `plain`；无法写出这些字符的输出流会得到 `+ - |`。

**交互菜单。**在终端里不带命令运行 `reverbscope` 会打开一个编号菜单：演示、测试信号、分析录音、通过音频接口测量、查看和比较会话、项目总览、设置、环境报告和桌面版。每一项会询问所需的信息（拖进终端的路径，带引号或反斜杠都能识别），打印等价的命令行以便下次直接输入，运行后回到菜单。测量在回答 `y` 之前不会播放任何声音。在提问处按 Ctrl+C 回到菜单；`q` 或输入结束则退出。在管道或脚本中，`reverbscope` 仍然打印简短的首页并以用法错误码退出；`REVERBSCOPE_NO_MENU=1` 可在终端里关闭菜单。

重定向或经过管道的输出是 UTF-8。Windows PowerShell 会按控制台代码页解码，中文因此变成乱码（`> report.txt`、`| Select-String`）；请先在该窗口运行一次 `$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()`，详见[在 PowerShell 中保存报告](../INSTALLATION.zh-CN.md#终端版)。命令提示符不受影响。

## 故障排查

| 现象 | 检查什么 |
| --- | --- |
| 直达声置信度不高 | 扫频配套文件不对；扬声器失真；想裁切录音？不要裁切。 |
| 参考扫频不对 | WAV 旁边的 `.reverbscope-sweep.json` 必须是 ReverbScope 为*这一次*扫频写出的文件（相同的时长、频带和淡入淡出）。用另一个会话的扫频，或把录音本身当作参考，都会把脉冲响应定位错。 |
| 一次导出中有多遍扫频 | 扫频只播放一次。同一个 WAV 中有多遍扫频时，ReverbScope 只分析其中一遍（在与最响一遍电平相近的各遍中，选其后录到的衰减最长的一遍，通常是最后一遍），忽略其余各遍，脉冲响应在下一遍开始处截止，并给出警告。每次只导出一次录音。 |
| 削波警告 | 降低回放增益或输入增益。 |
| 衰减范围不足 | 加长扫频、稍微提高回放电平，或换一个更安静的房间。 |
| 设备采样率不匹配 | 界面会在请求的采样率旁边显示设备采样率；请选择设备支持的采样率。 |
| 回送被拒绝 | 回送必须像一个电脉冲，而不是房间响应。如果第二个声道是另一支话筒，补偿会被拒绝，分析在未补偿的情况下继续。 |

## 报告问题

**帮助 ▸ 用于问题报告的环境报告**显示维护者首先需要的信息：ReverbScope 版本和构建提交、操作系统、库版本、设置和音频设备（*探测采样率*会加上每个设备接受的采样率；不会播放任何声音）。用*复制*把它粘贴到 issue 中；*打开 GitHub Issue 页面*会打开模板选择页。在终端中，同样的报告是 `reverbscope doctor`（`--probe`；要 JSON 用 `reverbscope --format json doctor`）。ReverbScope 不会自动发送任何内容；发布之前请通读文本，因为设备名称中可能包含个人姓名。

`reverbscope session bundle session/ --out report.zip` 把会话文件夹打包为 zip。如果不想分享房间录音，用 `--no-audio` 去掉 WAV 文件。和环境报告一样，其中 JSON 文件里的路径把你的主文件夹显示为 `~`。把 zip 附在测量问题（measurement）类 issue 上。设置和滚动日志保存在 `$REVERBSCOPE_HOME`（默认为 `~/.reverbscope`）下；环境报告中的*打开数据文件夹*按钮会打开它。

用真实的音频接口或通过 DAW 运行过 ReverbScope？请用 *Audio interface test report*（[音频接口测试报告，中文表单](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware-zh-CN.yml)）或 *DAW compatibility report*（[DAW 兼容性报告，中文表单](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw-zh-CN.yml)）模板记录下来；这些真实运行是 [HARDWARE_TESTS.zh-CN.md](../HARDWARE_TESTS.zh-CN.md) 的唯一来源。
