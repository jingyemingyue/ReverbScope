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

桌面版首次启动时，开始面板（尚未打开任何内容时窗口的中间区域）会显示一张“你的第一次测量”卡片：演示、DAW 路线和独立路线各有一个按钮，还有本指南的链接。“不再显示”会隐藏它；“帮助 ▸ 入门”可以把它找回来。

`reverbscope demo` 不需要音频接口和话筒，就能演示完整的工作流程。它会写出扫频，模拟一个虚构房间里
两个位置（一个靠近桌面和侧墙，一个向后移开）的话筒会录到什么，用与真实测量相同的代码分析这两个位置，
并对比它们。输出的导览最后会给出查看完整报告、对比结果、打开桌面应用以及开始你自己第一次测量的命令。

演示中的任何内容都不是测量结果：终端第一行就会说明这一点；每个保存的会话的模式都是
`synthetic_demo`，并附有说明它是模拟数据的备注；演示也绝不会覆盖不是它自己写出的文件夹。
用 `reverbscope demo --out <文件夹>` 可以指定文件的位置。演示给会话起的房间、位置和话筒名称，
用运行演示时的界面语言写入；打开、列出或生成报告时，则按当前界面语言显示。

## 通用 DAW 模式

1. `reverbscope sweep --sample-rate <project rate> --out sweep.wav`（或在界面的“通用 DAW 模式”中用“步骤 1 — 生成测试信号”生成，采样率选工程采样率）。把 `.reverbscope-sweep.json` 配套文件和 WAV 放在一起。
2. 把 WAV 导入 DAW 的一条新轨道，关闭时间伸缩（Warp、Flex、Follow Tempo），信号通路上不要有插件。把它路由到一只扬声器。
3. 在第二条轨道上接入测量话筒并开启录音待命，关闭输入监听，在扫频播放的同时录音。完整导出录音轨，不要裁切，也不要标准化。
4. 可选回送（loopback）：导出双声道文件（话筒 + 电回送），并使用 `--channel 0 --loopback-channel 1`。
5. `reverbscope analyze --recording take.wav --sweep sweep.wav --out session/`，或在界面的“通用 DAW 模式”中用“选择录音…”和“选择参考扫频…”选择这些文件。

**Pro Tools、Logic Pro / GarageBand、Cubase / Nuendo、Fender Studio Pro（原 PreSonus Studio One）、Ableton Live、REAPER、FL Studio、Bitwig Studio、Digital Performer 和 Audacity 的分步说明，以及报告中各条提示在 DAW 里对应的原因，见 [daw-setup.zh-CN.md](daw-setup.zh-CN.md)。**

## 独立模式与回送线

`reverbscope devices` 列出音频接口。`reverbscope measure --out session/` 播放扫频并录音。`--input-channels 1,2 --loopback-channel 2` 在输入 2 上录制电回送。

这次测量的 `sweep.wav` 和 `recording.wav` 只会连同描述它们的会话一起写入该文件夹：中途停止或被拒绝的测量不会改动文件夹。对已有会话的文件夹再次测量会替换该会话。文件夹里已有扫频或录音文件、却没有会话时（例如你用 `reverbscope sweep --out folder/sweep.wav` 生成的扫频），在播放任何声音之前就会被拒绝。

先把监听电平调低。高于 −12 dBFS 的电平每次都需要 `--acknowledge-level` 确认；该确认从不保存。

**演示**（界面中的“演示（无需音频接口）”，或 `reverbscope --backend fake measure`）在合成房间上运行同一流程，不会向扬声器发送任何信号。

### 各平台注意事项

`reverbscope devices` 在“主机 API”一列显示每个设备所属的音频系统；桌面应用把设备显示为 `[序号] 名称 (主机 API)`。

* **Windows。** 每个音频接口会按每种主机 API 各列一次。优先选主机 API 为 Windows WASAPI（或 Windows WDM-KS）的条目；避免 MME 和 Windows DirectSound，它们要经过 Windows 混音器。共享模式下 WASAPI 只能以设备的共享模式格式运行（[Microsoft：Device formats](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats)）：请在“声音”控制面板中把它设为测量采样率（控制面板 ▸ 硬件和声音 ▸ 声音 ▸ 该设备 ▸ 属性 ▸ 高级 ▸ *默认格式*），并把*音频增强*设为关闭（设置 ▸ 声音 ▸ 该设备）（[Microsoft 支持](https://support.microsoft.com/en-us/windows/fix-sound-or-audio-problems-in-windows-73025246-b61c-40fb-671a-2535c7cd56c8)）。允许桌面应用使用麦克风（设置 ▸ 隐私和安全性 ▸ 麦克风）。安装包不含 ASIO 支持（ASIO DLL 用 Steinberg 的专有 SDK 构建，已被移除，见 DEPENDENCIES.md §3）；只能通过 ASIO 工作的音频接口请用通用 DAW 模式测量。
* **macOS。** Core Audio。在“系统设置 ▸ 隐私与安全性 ▸ 麦克风”中允许 ReverbScope；没有该权限时录音是静音，ReverbScope 会报告 *“recording is silent”*。在“音频 MIDI 设置”中设定音频接口的采样率；输入和输出是不同设备时，可在那里把它们合成一个聚合设备。
* **Linux。** 通过系统的 PortAudio（`libportaudio2`）使用 ALSA。`hw:` 设备使用音频接口自身支持的采样率；`pipewire`、`pulse` 或 `default` 经过声音服务器，可能被重采样：ReverbScope 在测量前会把设备采样率显示在请求的采样率旁边。你的用户可能需要加入 `audio` 组。

## 读懂结果

每个指标都有有效性标记。`insufficient_decay_range`（衰减范围不足）表示数值被扣下不报，而不是等于零。没有单一总分。录音配置可能在宽带 C50 或 C80 不适合该类录音时给出一条提示；阈值是该配置的工程选择，不是评分。

**录音配置。**配置是指房间被用来判断的录音类型：人声、配音、原声吉他、鼓、房间话筒、合唱，或通用。每个配置对衰减、强早期反射、清晰度（C50 或 C80；鼓既不判断清晰度也不判断本底噪声）和低频都有自己的阈值。测量之前，配置选择框旁的“它关注什么？”按钮（以及检查器“测量条件”一节中的“关于这个配置...”）会说明所选配置关注什么、不判断什么，并给出具体数字；`reverbscope profiles` 列出所有配置，`reverbscope profiles vocal` 说明其中一个（`--format json` 输出数字）。这些阈值是工程取舍，见 [MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §8，从不是评分。

**测量健康**紧跟在关键数值之后：是“总览”视图中四个关键数值下方的卡片、检查器的第一节，也是文本报告中紧接“概览”之后的一节。它列出分析对这次录音本身所做的检查（参考信号、扫频、播放速度、直达声、电平、失真、采样丢失、衰减范围、本底噪声、录音长度，以及参与了测量时的回送和音频设备），每项为*良好*、*警告*、*无效*或*未知*，并给出原因、受影响的指标和下一步该做什么。*无效*表示某个数字不可信（录音削波、扫频播放速度不对）；*未知*表示无法进行该项检查（导入的脉冲响应）。扫频播放速度不对时，会列出各 DAW 设置采样率或关闭时间伸缩的位置，与[用 DAW 测量](daw-setup.zh-CN.md)中的步骤一致；分析无法完成时，这些步骤也会显示在错误信息之下。最差的一项决定整体状态；没有总分。

核心诊断（`warnings`、`notes`、`reason`）在 `result.json` 中保持英文，便于跨语言对照问题报告。界面和文本报告按界面语言显示它们。

### 工作台

桌面版是一个窗口。左侧的**导航栏**列出已打开项目的各个位置，以及所有已打开的测量：已保存的会话、刚测完的这次测量，以及用“文件 ▸ 打开会话…”打开的会话（它们会加入列表，不会替换已打开的内容）。每一行有一种颜色，即它的曲线在所有图表中的颜色；勾选框会把它和当前测量画在一起（叠加）。单击一行使其成为当前测量；右键单击可以把它设为基准、保存未保存的测量、显示文件夹、在它的位置再测一次，或把它从列表中移除（不会删除磁盘上的任何文件）。

中间的视图栏在下列视图之间切换（也可用“视图”菜单，或 Ctrl+1 到 Ctrl+9）。右侧的**检查器**显示当前测量：测量健康、带有效性的关键数值、录音条件和录音配置、设定基准时与基准的对比、选中的早期反射，以及房间检查。底部的**测量条**包含方式（音频接口、演示或 DAW 录音）、设备、采样率、话筒和回采输入、位置，以及“开始”/“停止”（Ctrl+Return、Esc）。“设置...”打开该方式的完整设置。

三栏的宽度可以调整；各栏大小、当前视图和窗口会在下次启动时恢复（“视图 ▸ 重置布局”恢复默认）。尚未保存的测量标为*未保存*：开始新的测量、选择“新测量”、移除它或退出时，会先询问是否保存（打开会话或项目时它会留在列表中）。

工作台有十一个视图：

| 视图 | 显示内容 |
| --- | --- |
| 总览 | 关键数值（混响、本底噪声、早期反射、直达声）及其可信程度、测量健康卡片、解读，以及宽带与倍频程频带的 EDT / T20 / T30 / RT60 和 C50 / C80 / D50 / 重心时间表格，各自带有效性。 |
| 频率响应 | 每个被绘制测量的幅度，使用其列表颜色，图例中注明显示平滑方式（存储的曲线不变）。“显示存储的曲线”会加上未平滑的存储曲线（点线）。进行了回采补偿时，虚线是电回采。设定基准后，差值窗格显示当前测量减去基准。0 dB 指音频接口，而不是“房间里是平直的”。 |
| 脉冲响应 | 反卷积得到的脉冲响应（IR）及其能量时间曲线和早期反射（延迟 ms，相对直达声的 dB；候选用空心标记）。单击一个反射即选中它：检查器和“房间”视图显示同一个反射。峰值是直达声；波形按该峰值缩放绘制，曲线的图例会注明。 |
| 衰减 | 被绘制测量在某一频带的 Schroeder / 能量衰减曲线，所选指标的评估范围以阴影标出，并按频带列出 T 值。“当前测量的全部频带”把宽带画成实线，每个倍频程频带使用各自的虚线样式，不只靠颜色区分；没有曲线或没有 RT60 的频带会说明原因。 |
| 噪声 | 安静段的频谱和 50/60 Hz 交流哼声候选。 |
| 时频谱 | 脉冲响应的时间-频率图，在后台计算。 |
| 瀑布图 | 脉冲响应的累积频谱衰减，在后台计算。 |
| 房间 | 三维房间：你输入的内容（实线）、测量所约束的内容（虚线），以及仅在假设房间为长方体时才成立的内容（点线）。见[房间视图](#房间视图)。 |
| 项目 | 项目总览：各位置、它们的测量、在录音配置下的契合度、ISO 3382-2 等级，以及下一步该测什么。 |
| 对比 | 当前测量对基准：判定、衰减、噪声、早期反射、共振和差值图。 |
| 完整报告 | 与 `reverbscope analyze` 输出的文本报告相同，警告列在末尾。“复制报告”可复制全文。 |

所有图表都可以用滚轮（以光标为中心）缩放、拖动平移、双击、按 R 或点“重置视图”重新适配，并显示光标处带单位的数值。“导出”可以把图表保存为 PNG 或 SVG，或把所绘曲线保存为 CSV（瀑布图的切片不含透视偏移；时频谱是图像，没有 CSV）。

低频共振候选列在“完整报告”中（以及 `reverbscope export` 之后的 `resonances.csv`），没有单独的视图。

### 房间视图

“房间”视图绘制你输入的房间尺寸（长、宽、高，单位 m）、扬声器和每个位置的话筒；可以从示例房间开始，也可以导入 PLY 或 OBJ 扫描（作为输入的几何绘制，不从中测量任何内容）。拖动可旋转，右键拖动可平移，滚轮缩放，双击适配；在平面视图中可以拖动扬声器和话筒。输入的内容保存在项目（或会话）旁的 `room-geometry.json` 中，从不写入会话。

有测量时，虚线层显示测量所约束的内容：有回采时，直达距离是以扬声器为中心的球面；选中的反射是以扬声器和话筒为焦点的椭球面；有摆位结果时，是它允许的扬声器位置环。点线层显示长方体房间会有的一阶反射路径；与选中反射相符的面会被高亮。单支话筒无法定位墙面：一个反射只说明它的反射面与椭球面相切，与房间某个面的对应只在房间确实是你画的长方体时才成立。检查器的房间检查会把输入的距离与测得的距离相比较。

## 摆位

摆位结果在“房间”视图的侧栏中。没有卷尺实测的扬声器距离时，ReverbScope 只报告每个到达声的多余路径。有了距离（垂直方向还需要话筒高度）之后，它会报告扬声器高度、两个设备上方的平面和水平间距。它从不指明墙面，也不给出房间长度或宽度。

请在通用 DAW 模式或独立模式中、点击“分析”之前填入卷尺数值，或在命令行中使用 `--speaker-distance` / `--mic-height` / `--temperature`。

## 对比两个位置

`reverbscope compare baseline/ candidate/ --same-input-gain`（或在桌面版中右键单击一个测量 ▸ “设为基准”，让另一个成为当前测量，再打开“对比”视图；“文件 ▸ 对比会话…”可以选择两个已保存的会话）。只有两侧都是 VALID 时，衰减差值才是 VALID。噪声差值需要明确声明“输入增益未变”。任何变化都不会被称为显著；ISO 3382-1 给出的 T 的刚可察觉差只作为参考背景引用。

**判定。**在候选会话的录音配置下，对比会对混响、清晰度、早期反射、本底噪声和低频分别给出：*有意义的改善*、*有意义的退化*、*大概率无关紧要*、*不可比较*，或*证据不足*，并每次说明原因（“对比”视图的判定卡片，以及检查器的“对比”一节；报告中紧接“概览”之后的一节；`--format json` 中的 `verdict`）。判定依据配置的阈值（人声棚不在乎 0.30 s 变成 0.22 s；房间话筒会把变得过干的房间判为退化）、刚可察觉差，以及两次测量都在手时的测量健康；它从不根据一对位置就称某个变化“显著”（[MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §11a）。

“对比”视图列出配对的早期反射（延时相差 ±0.5 ms 以内）和低频共振（相差 1/6 倍频程以内，并带有 decay-distinguishable 标志）。低频共振只在两次测量都搜索过的范围内比较：在另一次测量从未搜索的频率（例如其扫频起点更高）发现的共振既不算消失也不算新出现；若有一次测量根本没有搜索，低频一栏显示“未比较”（报告中如此，“共振”标签页的表格下方也有同样的说明；两次测量的直达声并非都可信时，“早期反射”标签页同样给出说明）。`reverbscope compare … --out comparison.json` 只写入数值；`reverbscope show comparison.json` 会再次打印报告并**重新推导**解读（解读从不存入该文件）。

## 项目、位置与总览

项目文件夹包含 `project.json` 和普通的会话文件夹；该文件记录每个会话是在哪个位置测的。用 `reverbscope project init --out room/ --name Booth` 新建（或“文件 ▸ 打开项目...”，对普通文件夹它会提议建成项目），再把会话归入位置：`reverbscope project add room/ session/ --position desk`。对已有 `project.json` 的文件夹再次运行 `project init` 会被拒绝；加 `--force` 则重新开始这个项目，原有的位置不再保留。

**测量多个位置。**在“项目”视图点“测量新位置...”，给位置起名（A、B、桌前……）并选择测量方式（在导航栏中右键单击一个位置，会用测量条的方式做同样的事）；扬声器、它的电平和输入增益保持不变，只移动话筒。随后“文件 ▸ 保存会话...”会把会话保存到项目里、以位置命名的文件夹中（`B-1`、`B-2`……），并在导航栏中记入该位置。同一位置测两次可以看出测量是否可重复：总览会说明两次是否在 T 的 5 % 刚可察觉差之内一致，不一致时也会直说。

**总览**（`reverbscope project overview room/`；“项目”视图）在一个录音配置下（默认为最新一次测量自身的配置，或 `--profile`）读取每次测量：测量健康、RT60、清晰度、本底噪声和最强早期反射，以及它的*契合度*：配置对它没有警告则为*契合*，有警告则列出主题，测量无效或没有有效（VALID）混响时间则为*无法判断*。每个位置由其最健康、最新的一次测量代表；第一个位置之后的每个位置都带有其测量相对第一个位置的判定（与“对比”视图相同的判定，并计入两次测量的健康）。随后是空间平均和 ISO 3382-2 等级，以及各位置 RT60 在房间内的差异；“下一步”说明接下来该测什么：为达到下一等级再测一个话筒位置（或第二个扬声器位置）、重复测量一次、重新测量某个位置、哪些位置契合。页面不为位置排名：两个都契合的位置之间，请根据判定和录音的需要来选。`--format json` 输出整个总览；`project.json` 除位置外不存储任何内容（[MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §13）。

`reverbscope project average room/` 只平均有效（VALID）的 T 值，从不平均衰减曲线，并注明测量位置数达到的 ISO 3382-2 等级。RT60 一列是各会话自身 RT60（优先 T30，否则 T20）的平均值。`n` 是该行参与平均的会话数；参与会话较少的数值会附上自己的会话数，例如 `0.91 s (1)`。

## 导出与语言

`reverbscope export session/ --format csv --out curves/` 导出每一条曲线。把另一个会话导出到同一文件夹时，该会话没有的曲线文件会被删除（`--no-curves` 会话没有任何曲线），因此文件夹里不会混有两个会话的数据。

ReverbScope 跟随系统语言：Mac 上是首选语言（“系统设置 → 通用 → 语言与地区”；“终端”、iTerm 和 VS Code 不管首选语言是什么都会设置 `LANG=en_US.UTF-8`，所以 `LANG` 排在首选语言之后），Windows 上是显示语言，Linux 上是 `LANGUAGE`、`LC_ALL`、`LC_MESSAGES` 和 `LANG`。和其他程序一样，`LC_ALL=C`（或 `LC_MESSAGES=C`）在任何系统上都给出英文，例如提交错误报告时运行 `LC_ALL=C reverbscope show session/`。想不管系统怎么设置都固定使用一种语言，保存一次即可：

```bash
reverbscope config language zh_CN   # 中文
reverbscope config language en      # English
reverbscope config language auto    # 改回跟随系统
```

`reverbscope config language` 显示当前使用的语言以及原因。桌面版的“设置 → 语言”写入的是同一个设置。`--lang zh_CN` 只对一条命令指定语言，`REVERBSCOPE_LANG` 对一个终端会话指定语言；优先顺序是 `--lang`、已保存的设置、`REVERBSCOPE_LANG`、系统语言。主屏幕（直接运行 `reverbscope`）和 `reverbscope --help` 的最后一行用另一种语言写出切换到该语言的命令。

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
