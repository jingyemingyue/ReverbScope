# RoomScope 用户指南

[English](en.md) | **简体中文**

RoomScope 用来测量录音房间，让你听清房间对近距离拾音的声源做了什么。它不给房间打分，也不做校正。

本页是中文指南，英文原文见 [en.md](en.md)；两者不一致时以英文版为准。

## 安装

RoomScope 提供**两条 beta**（都还是 beta）。**稳定 beta** 是最近一次已发布的预发布（更少缺陷、功能面更窄）。**预览 beta** 是当前开发线（功能更强，可能不稳定）；没有发布预览版 GitHub Release。

从项目的 [Releases 页面](https://github.com/jingyemingyue/RoomScope/releases)下载**稳定 beta**。各系统的分步说明、更新、卸载和故障排查见 [INSTALLATION.zh-CN.md](../INSTALLATION.zh-CN.md)，本节是简要版。每个 Release 都附有一个 `SHA256SUMS` 文件，请与下载文件的校验值比对（macOS / Linux：`shasum -a 256 <file>`；PowerShell：`Get-FileHash <file>`）。

RoomScope 有两个版本。**桌面版**就是本指南介绍的应用程序，同时包含命令行；**终端版**只有命令行（没有窗口和图表），
适合脚本、服务器和没有图形桌面的电脑。

| 系统 | 桌面版 | 启动 RoomScope |
| --- | --- | --- |
| Windows 10/11 x64 | `RoomScope-Desktop-Windows-x64-Setup.exe`（安装程序）或 `RoomScope-Desktop-Windows-x64.zip` | 开始菜单 → RoomScope，或运行 zip 中的 `roomscope-gui.exe` |
| macOS 14+，Apple 芯片 | `RoomScope-Desktop-macOS-arm64.dmg` | 把 RoomScope 拖进“应用程序”文件夹，然后打开 |
| macOS 14+，Intel | `RoomScope-Desktop-macOS-x86_64.dmg` | 把 RoomScope 拖进“应用程序”文件夹，然后打开 |
| Linux x86_64 | `RoomScope-Desktop-Linux-x86_64.tar.gz` | `tar xzf RoomScope-Desktop-Linux-x86_64.tar.gz && roomscope/roomscope-gui` |

| 系统 | 终端版 | 启动 RoomScope |
| --- | --- | --- |
| Windows 10/11 x64 | `RoomScope-Terminal-Windows-x64.zip` | 解压后双击 `RoomScope Terminal.cmd`，输入 `roomscope.exe demo` |
| macOS 14+，Apple 芯片 | `RoomScope-Terminal-macOS-arm64.tar.gz` | 用 `tar xzf` 解压，然后运行 `roomscope-terminal/roomscope demo` |
| macOS 14+，Intel | `RoomScope-Terminal-macOS-x86_64.tar.gz` | 用 `tar xzf` 解压，然后运行 `roomscope-terminal/roomscope demo` |
| Linux x86_64 | `RoomScope-Terminal-Linux-x86_64.tar.gz` | 用 `tar xzf` 解压，然后运行 `roomscope-terminal/roomscope demo` |

Windows 和 Linux 的桌面版安装包含两个程序：桌面程序 `roomscope-gui` 和命令行工具 `roomscope`（在终端运行 `roomscope --help`）。在 macOS 上，应用的可执行文件带参数运行时就是命令行工具：`/Applications/RoomScope.app/Contents/MacOS/RoomScope --help`。

在维护者取得签名证书之前，**这些安装包都没有用于分发的签名**（macOS 应用只有临时签名（ad hoc），未经公证；Windows 文件没有 Authenticode 签名），因此首次打开时操作系统会发出警告：

* **macOS：** 先打开一次应用；macOS 提示无法验证时选“完成”，然后进入“系统设置 → 隐私与安全性”，点“仍要打开”（该按钮在第一次尝试打开之后才会出现）并确认。从 macOS 15 Sequoia 起，右键 → “打开”不再能绕过这一检查；在 macOS 14 上仍然可用（[Apple](https://developer.apple.com/news/?id=saqachfa)）。系统询问时请允许麦克风访问（安装包的 Info.plist 中声明了 `NSMicrophoneUsageDescription`）。打包的 NumPy 和 SciPy 需要 macOS 14 或更新版本；DMG 只在 macOS 15（Intel）和 macOS 26（Apple 芯片）的 CI 运行器上构建和启动过。
* **Windows：** SmartScreen 可能发出警告，请选“更多信息”→“仍要运行”。安装程序只为当前用户安装，不需要管理员权限；可在“设置 → 应用”中卸载。
* **Linux：** tar 包需要系统自带的 PortAudio、OpenGL/EGL 和 XCB 库（Debian / Ubuntu：`sudo apt install libportaudio2 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0`）；图表中要显示中文，还需要中文字体，例如 `fonts-noto-cjk`。`packaging/linux/roomscope.desktop` 是一个可以按需修改的桌面启动项。

**用 Python 安装。** RoomScope 还没有发布到 PyPI。使用 Python 3.12 或更新版本，把 Release 附带的 wheel 安装到虚拟环境中：

```bash
python3 -m venv roomscope-env
roomscope-env/bin/pip install "./roomscope-<version>-py3-none-any.whl[gui]"
roomscope-env/bin/roomscope gui
```

只需要命令行和 Python API 时去掉 `[gui]`。`pip install -e ".[gui]"` 是从克隆的源码进行的开发者安装。

“关于”对话框和 `THIRD_PARTY_LICENSES/` 列出了 Qt、libsndfile 以及其他随包组件的许可证。

## 先试一试：演示

`roomscope demo` 不需要音频接口和话筒，就能演示完整的工作流程。它会写出扫频，模拟一个虚构房间里
两个位置（一个靠近桌面和侧墙，一个向后移开）的话筒会录到什么，用与真实测量相同的代码分析这两个位置，
并对比它们。输出的导览最后会给出查看完整报告、对比结果、打开桌面应用以及开始你自己第一次测量的命令。

演示中的任何内容都不是测量结果：终端第一行就会说明这一点；每个保存的会话的模式都是
`synthetic_demo`，并附有说明它是模拟数据的备注；演示也绝不会覆盖不是它自己写出的文件夹。
用 `roomscope demo --out <文件夹>` 可以指定文件的位置。

## 交互菜单

在终端里直接运行 `roomscope`（不带命令），RoomScope 会用界面语言显示一个编号菜单：

```text
测量
  1  体验演示         用合成数据，不需要声卡
  2  生成测试信号     在 DAW 中播放并录音用的扫频 WAV
  3  分析录音         播放扫频时录下的 WAV
  4  用声卡直接测量   由 RoomScope 播放扫频并录音

结果
  5  查看结果         已保存的会话或对比
  6  对比两个位置     两次测量之间有什么变化
  7  打开桌面应用     用图表查看结果

设置与诊断
  8  设置             语言、录音配置、音频后端、输出文件夹
  9  环境报告         反馈问题时附上

  0  退出             也可以输入 q
```

终端版没有第 7 项。

输入编号并按回车即可。每一项只询问它需要的内容，括号里是默认值，直接按回车就采用它：演示文件夹、扫频写到哪里以及采样率、录音和录音时播放的扫频（录音旁边的 `sweep.wav` 会自动找到）、会话文件夹（第一个还不存在的 `session-N`；设置了输出文件夹时放在那里）。路径可以直接输入、带引号粘贴，或者把文件拖进终端窗口；`~` 和中文文件夹名都可以。文件不存在或编号超出范围时，菜单会说明原因并重新询问。

运行任何操作之前，菜单都会先显示等同的命令，例如“等同于命令：roomscope analyze --recording take.wav --sweep sweep.wav --out session-1”，下次可以直接输入。命令的运行方式和手动输入完全相同；失败时菜单会用文字说明，并等你按回车。

**用声卡直接测量** 会像 `roomscope devices` 一样列出设备，然后询问输入和输出设备（直接回车使用系统默认）、话筒所在的输入声道、电平（默认 -20 dBFS；高于 -12 dBFS 时会先问监听音量是否已经调低）和文件夹，再显示测量计划；只有输入 `y` 才会播放。**查看结果** 和 **对比两个位置** 会列出当前文件夹和输出文件夹中的会话（最新的在前），可以输入编号或路径。**设置** 通过 `roomscope config` 修改界面语言（简体中文、English、其他界面语言或跟随系统）、默认录音配置、音频后端和输出文件夹。

在提问时按 Ctrl+C 返回菜单；在菜单本身按 Ctrl+C 则退出。Ctrl+D（Windows 上是 Ctrl+Z 再按回车）在任何地方都会退出。`roomscope menu` 可以明确打开菜单。在管道、文件或脚本中，使用了 `--format json`，或者设置了 `ROOMSCOPE_NO_MENU=1` 时，直接运行 `roomscope` 仍显示简短的概览。`roomscope menu` 不看 `ROOMSCOPE_NO_MENU`，但在无法输入回答的地方或使用了 `--format json` 时会拒绝运行，退出码为 2。

## 通用 DAW 模式

**扫频采样率**必须与你正在使用的 DAW 工程一致。这是 RoomScope 已经当作依赖 DAW 的唯一会话设置（导出位深和时间伸缩是你的操作说明，不是从宿主抄来的值）。RoomScope 不连接 DAW，也不扫描正在运行的程序。

- `roomscope daw` 列出已声明或伪（fake）工程，或说明未找到。除非设置了 `ROOMSCOPE_FAKE_DAWS`（仅测试 / 演示：`名称:采样率` 或 `名称:采样率:工程`，用 `;` 分隔），本机不会被当作正在运行 DAW。
- 若未找到或同时有多个工程，RoomScope **会询问**要跟随哪一个，不会猜测。命令行：`--follow-daw --daw 名称`；同一名称有多个工程时再加 `--daw-project 标题`。未检测到工程时，`--daw 名称 --sample-rate 采样率` 就是你给出的答案。
- 界面里，通用 DAW 模式步骤 1 的 **选择要跟随的 DAW...**（在“保存测试信号”之前）。多个伪工程是选择列表；一个都没有时，请输入名称和采样率。

1. `roomscope sweep --follow-daw --daw <名称> --out sweep.wav`（或 `roomscope sweep --sample-rate <工程采样率> --out sweep.wav`，或在界面的“通用 DAW 模式”中先选择 DAW 再生成）。把 `.roomscope-sweep.json` 配套文件和 WAV 放在一起。
2. 把 WAV 导入 DAW 的一条新轨道，关闭时间伸缩（Warp、Flex、Follow Tempo），信号通路上不要有插件。把它路由到一只扬声器。
3. 在第二条轨道上接入测量话筒并开启录音待命，关闭输入监听，在扫频播放的同时录音。完整导出录音轨，不要裁切，也不要标准化。
4. 可选回送（loopback）：导出双声道文件（话筒 + 电回送），并使用 `--channel 0 --loopback-channel 1`。
5. `roomscope analyze --recording take.wav --sweep sweep.wav --out session/`，或在界面的“通用 DAW 模式”中用“选择录音…”和“选择参考扫频…”选择这些文件。

**Pro Tools、Logic Pro / GarageBand、Cubase / Nuendo、Studio One、Ableton Live、REAPER、FL Studio、Bitwig Studio 和 Audacity 的分步说明，以及报告中各条提示在 DAW 里对应的原因，见 [daw-setup.zh-CN.md](daw-setup.zh-CN.md)。**

## 独立模式与回送线

`roomscope devices` 列出音频接口。`roomscope measure --out session/` 播放扫频并录音。`--input-channels 1,2 --loopback-channel 2` 在输入 2 上录制电回送。

先把监听电平调低。高于 −12 dBFS 的电平每次都需要 `--acknowledge-level` 确认；该确认从不保存。

**演示**（界面中的“演示（无需音频接口）”，或 `roomscope --backend fake measure`）在合成房间上运行同一流程，不会向扬声器发送任何信号。

### 各平台注意事项

`roomscope devices` 会在方括号中显示每个设备所属的音频系统（主机 API）。

* **Windows。** 每个音频接口会按每种主机 API 各列一次。优先选 `[Windows WASAPI]`（或 `[Windows WDM-KS]`）；避免 `[MME]` 和 `[Windows DirectSound]`，它们要经过 Windows 混音器。共享模式下 WASAPI 只能以设备的共享模式格式运行（[Microsoft：Device formats](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats)）：请在“声音”控制面板中把它设为测量采样率（控制面板 ▸ 硬件和声音 ▸ 声音 ▸ 该设备 ▸ 属性 ▸ 高级 ▸ *默认格式*），并把*音频增强*设为关闭（设置 ▸ 声音 ▸ 该设备）（[Microsoft 支持](https://support.microsoft.com/en-us/windows/fix-sound-or-audio-problems-in-windows-73025246-b61c-40fb-671a-2535c7cd56c8)）。允许桌面应用使用麦克风（设置 ▸ 隐私和安全性 ▸ 麦克风）。安装包不含 ASIO 支持（ASIO DLL 用 Steinberg 的专有 SDK 构建，已被移除，见 DEPENDENCIES.md §3）；只能通过 ASIO 工作的音频接口请用通用 DAW 模式测量。
* **macOS。** Core Audio。在“系统设置 ▸ 隐私与安全性 ▸ 麦克风”中允许 RoomScope；没有该权限时录音是静音，RoomScope 会报告 *“recording is silent”*。在“音频 MIDI 设置”中设定音频接口的采样率；输入和输出是不同设备时，可在那里把它们合成一个聚合设备。
* **Linux。** 通过系统的 PortAudio（`libportaudio2`）使用 ALSA。`hw:` 设备使用音频接口自身支持的采样率；`pipewire`、`pulse` 或 `default` 经过声音服务器，可能被重采样：RoomScope 在测量前会把设备采样率显示在请求的采样率旁边。你的用户可能需要加入 `audio` 组。

## 读懂结果

每个指标都有有效性标记。`insufficient_decay_range`（衰减范围不足）表示数值被扣下不报，而不是等于零。没有单一总分。录音配置可能在宽带 C50 或 C80 不适合该类录音时给出一条提示；阈值是该配置的工程选择，不是评分。

核心诊断（`warnings`、`notes`、`reason`）在 `result.json` 中保持英文，便于跨语言对照问题报告。界面和文本报告按界面语言显示它们。

结果页有九个标签页：

| 标签页 | 显示内容 |
| --- | --- |
| 总览 | 关键数值（混响、本底噪声、早期反射、直达声）及其可信程度、解读，以及宽带与倍频程频带的 EDT / T20 / T30 / RT60 和 C50 / C80 / D50 / 重心时间表格，各自带有效性。 |
| 完整报告 | 与 `roomscope analyze` 输出的文本报告相同，警告列在末尾。“复制报告”可复制全文。 |
| 脉冲响应 | 反卷积得到的脉冲响应（IR）。峰值是直达声；不会归一化到 1.0。 |
| 频率响应 | 原始（点线）与平滑（实线）幅度。进行了回送补偿时，虚线是电回送。0 dB 指音频接口，而不是“房间里是平直的”。 |
| 频谱 | 同一脉冲响应的 Welch 功率谱（AES17 密度）。不是加窗频率响应标签页，也不是安静段噪声 PSD。 |
| 衰减 | Schroeder / 能量衰减曲线。宽带为实线；各倍频程频带使用不同的虚线样式，不只靠颜色区分。 |
| 噪声 | 安静段的频谱和 50/60 Hz 交流哼声候选。 |
| 早期反射 | ETC 峰值（延时 ms，相对直达声的 dB）。候选用空心标记表示。 |
| 摆位 | 多余路径；只有在输入了卷尺实测的扬声器距离时，才给出扬声器高度、两个设备上方的平面以及水平间距。不指明任何墙面。若已有 ASCII PLY 或 OBJ 扫描，会画成淡色点。 |

低频共振候选列在“完整报告”中（以及 `roomscope export` 之后的 `resonances.csv`），没有单独的标签页。

## 摆位

结果页有“摆位”标签页。没有卷尺实测的扬声器距离时，RoomScope 只报告每个到达声的多余路径。有了距离（垂直方向还需要话筒高度）之后，它会报告扬声器高度、两个设备上方的平面和水平间距。它从不指明墙面，也不给出房间长度或宽度。

请在通用 DAW 模式或独立模式中、点击“分析”之前填入卷尺数值，或在命令行中使用 `--speaker-distance` / `--mic-height` / `--temperature`。若要叠加上已有的扫描，在摆位页选择 ASCII PLY 或 OBJ，或使用 `--scan FILE`。RoomScope 不连接激光雷达；不读取二进制 PLY；坐标按文件原样当作米，不会对齐到话筒。

## 对比两个位置

`roomscope compare baseline/ candidate/ --same-input-gain`（或界面的“对比”页面）。只有两侧都是 VALID 时，衰减差值才是 VALID。噪声差值需要明确声明“输入增益未变”。任何变化都不会被称为显著；ISO 3382-1 给出的 T 的刚可察觉差只作为参考背景引用。

“对比”页面列出配对的早期反射（延时相差 ±0.5 ms 以内）和低频共振（相差 1/6 倍频程以内，并带有 decay-distinguishable 标志）。`roomscope compare … --out comparison.json` 只写入数值；`roomscope show comparison.json` 会再次打印报告并**重新推导**解读（解读从不存入该文件）。

## 项目与平均

项目文件夹包含 `project.json` 和普通的会话文件夹。
`roomscope project init --out room/ --name Booth`，然后
`roomscope project add room/ session/ --position desk`。
`roomscope project average room/` 只平均有效（VALID）的 T 值，从不平均衰减曲线，并注明测量位置数达到的 ISO 3382-2 等级。

## 导出与语言

`roomscope export session/ --format csv --out curves/` 导出每一条曲线。

RoomScope 跟随系统语言：Mac 上是首选语言（“系统设置 → 通用 → 语言与地区”；“终端”、iTerm 和 VS Code 不管首选语言是什么都会设置 `LANG=en_US.UTF-8`，所以 `LANG` 排在首选语言之后），Windows 上是显示语言，Linux 上是 `LANGUAGE`、`LC_ALL`、`LC_MESSAGES` 和 `LANG`。想不管系统怎么设置都固定使用一种语言，保存一次即可：

```bash
roomscope config language zh_CN   # 中文
roomscope config language en      # English
roomscope config language auto    # 改回跟随系统
```

其他界面语言是 `zh_TW`（繁体中文）、`ja`、`ko`、`es`、`fr` 和 `de`；`roomscope config language` 会列出它们，并显示当前使用的语言以及原因。桌面版的“设置 → 语言”写入的是同一个设置。`--lang zh_CN` 只对一条命令指定语言，`ROOMSCOPE_LANG` 对一个终端会话指定语言；优先顺序是 `--lang`、已保存的设置、`ROOMSCOPE_LANG`、系统语言。交互菜单和主屏幕（直接运行 `roomscope`）以及 `roomscope --help` 的最后一行用另一种语言写出切换到该语言的命令。

每种界面语言都会翻译解读、文本报告的标签、图形界面和全部命令行帮助（`roomscope --help` 及每个子命令，包括占位符和 argparse 自己的提示）。用户文档仍为英文和简体中文。单位不翻译；数字保持 ASCII。诊断说明和警告在 `result.json` 中以英文保存，显示时翻译。

`roomscope config` 列出桌面版保存的其他设置，并可以在命令行里修改它们，终端版也一样：`profile`（默认录音配置）、`backend`（`portaudio` 或 `fake`）、`output-folder`、`copy-recording` 和 `developer-tools`（`on` 或 `off`），以及 `theme`（`system`、`light` 或 `dark`，只影响桌面版）。例如 `roomscope config profile vocal`；`auto` 把一项设置恢复为默认值，`roomscope --format json config` 以 JSON 输出所有设置。

在终端里，命令行使用颜色和 ✓ ! × 符号；输出重定向到文件或其他程序时只写纯文本。`--color never` 或环境变量 `NO_COLOR` 关闭颜色，`--color always` 在管道中也保留颜色。

## 故障排查

| 现象 | 检查什么 |
| --- | --- |
| 直达声置信度不高 | 扫频配套文件不对；扬声器失真；想裁切录音？不要裁切。 |
| 参考扫频不对 | WAV 旁边的 `.roomscope-sweep.json` 必须是 RoomScope 为*这一次*扫频写出的文件（相同的时长、频带和淡入淡出）。用另一个会话的扫频，或把录音本身当作参考，都会把脉冲响应定位错。 |
| 一次导出中有多遍扫频 | 扫频只播放一次。同一个 WAV 中有多遍扫频时，RoomScope 只分析其中一遍（在与最响一遍电平相近的各遍中，选其后录到的衰减最长的一遍，通常是最后一遍），忽略其余各遍，脉冲响应在下一遍开始处截止，并给出警告。每次只导出一次录音。 |
| 削波警告 | 降低回放增益或输入增益。 |
| 衰减范围不足 | 加长扫频、稍微提高回放电平，或换一个更安静的房间。 |
| 设备采样率不匹配 | 界面会在请求的采样率旁边显示设备采样率；请选择设备支持的采样率。 |
| 回送被拒绝 | 回送必须像一个电脉冲，而不是房间响应。如果第二个声道是另一支话筒，补偿会被拒绝，分析在未补偿的情况下继续。 |

## 报告问题

**帮助 ▸ 用于问题报告的环境报告**显示维护者首先需要的信息：RoomScope 版本和构建提交、操作系统、库版本、设置和音频设备（*探测采样率*会加上每个设备接受的采样率；不会播放任何声音）。用*复制*把它粘贴到 issue 中；*打开 GitHub Issue 页面*会打开模板选择页。在终端中，同样的报告是 `roomscope doctor`（`--probe`、`--json`）。RoomScope 不会自动发送任何内容；发布之前请通读文本，因为设备名称中可能包含个人姓名。

`roomscope session bundle session/ --out report.zip` 把会话文件夹打包为 zip。如果不想分享房间录音，用 `--no-audio` 去掉 WAV 文件。把 zip 附在测量问题（measurement）类 issue 上。设置和滚动日志保存在 `$ROOMSCOPE_HOME`（默认为 `~/.roomscope`）下；环境报告中的*打开数据文件夹*按钮会打开它。

用真实的音频接口或通过 DAW 运行过 RoomScope？请用 *Audio interface test report*（[音频接口测试报告，中文表单](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware-zh-CN.yml)）或 *DAW compatibility report*（[DAW 兼容性报告，中文表单](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw-zh-CN.yml)）模板记录下来；这些真实运行是 [HARDWARE_TESTS.zh-CN.md](../HARDWARE_TESTS.zh-CN.md) 的唯一来源。
