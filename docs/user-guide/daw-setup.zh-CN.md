# 用 DAW 测量

[English](daw-setup.md) | **简体中文**

通用 DAW 模式面向任何能在播放一个 WAV 的同时录制另一个的 DAW。RoomScope 从不与 DAW 通信，它只需要完整导出的录音。本页先列出每个 DAW 都必须做对的事，再给出多数录音棚常用 DAW 的具体步骤。英文原文见 [daw-setup.md](daw-setup.md)；两者不一致时以英文版为准。

> **按文档编写的流程，尚未在 DAW 中实测。** 下面的步骤和菜单名称依据各厂商当前的官方文档编写，每一步都标有编号来源（少数第三方来源已注明）。其中没有任何一步已经在真实 DAW 中配合 RoomScope 运行过：[HARDWARE_TESTS.zh-CN.md](../HARDWARE_TESTS.zh-CN.md) 中的 DAW 矩阵是空的。如果你实际跑过，或者你的版本与此不同，请提交 [DAW 兼容性报告（中文表单）](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw-zh-CN.yml)或英文的 [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml)。
>
> 菜单名称保留各 DAW 英文界面中的写法，便于对照官方手册；中文界面的 DAW 请按对应位置查找。

## 每个 DAW 都必须做到

1. **采样率一致。** 扫频采样率是 RoomScope 必须跟随你正在使用的 DAW 工程的唯一会话设置。`roomscope daw` 列出已声明或伪工程；若未找到或同时有多个，RoomScope 会询问，不会猜测。`roomscope sweep --follow-daw --daw REAPER`（未检测到工程时用 `--daw 名称 --sample-rate`）按该工程的采样率写扫频。界面里，在保存测试信号之前使用 **选择要跟随的 DAW...**。你也可以自己指定采样率：`roomscope sweep --sample-rate 44100 --out sweep_44k.wav`，或在界面步骤 1 中选择采样率。48 kHz 的文件在 44.1 kHz 工程里未经转换直接播放会慢 8 %，无法反卷积；只要 `.roomscope-sweep.json` 与 WAV 放在一起（请保持这样），这时 RoomScope 会报告 *“a file generated at 48000 Hz was played at 44100 Hz”*。以另一种采样率导出录音不会有问题：DAW 在导出时会转换，RoomScope 会按文件的采样率处理。RoomScope 不查询正在运行的宿主；编写本文档的虚拟机没有 DAW。
2. **不做时间伸缩。** 测试信号片段必须关闭 Warp、Flex Time、Follow Tempo、Elastic Audio 及各种伸缩模式，导入后也不要再改速度。扫频速度偏差超过估计本身的离散范围（默认 10 秒扫频约 1.3 %，3 秒约 2.4 %，1 秒约 5.5 %）且使用了附带的 JSON 文件时，RoomScope 会报告 *“the DAW time-stretched it”*；更小的伸缩同样会毁掉测量（直达声置信度低、衰减不可靠），但不会被点名，所以请检查片段设置，不要只依赖报告。
3. **干净的回放链路。** 旁通测试信号轨道、它经过的总线以及主输出上的所有插件：限幅器、削波器、“响度”或磁带插件，以及**房间校正**插件（SoundID Reference、ARC 等）——除非你就是要测校正后的系统。测试信号上不要有淡入淡出、片段增益或自动化。推子或片段增益低于 0 dB 没有关系。
4. **只用一只扬声器。** 把测试信号轨道路由到要测的那一只扬声器（声像打到底或用单声道输出）。两只扬声器播放同一扫频会相互干涉，结果哪一只都不代表。
5. **在单独的单声道轨道上录话筒**，关闭输入监听（否则话筒会经扬声器回授），轨道上不要有插件、发送或门限。在测试信号开始前开始录音，或一次录完整个片段：文件开头的一秒静音就是为此准备的。只录一遍：关闭循环录音。如果为了静音监听把话筒通道推子拉到底，在经过该通道渲染的导出（分轨或轨道导出）之前，请把推子恢复到 0 dB。
6. **完整导出录音轨或片段**，采用工程采样率，格式为 WAV（Broadcast WAV、RF64、Wave64 均可）、AIFF、CAF 或 FLAC，24 位或 32 位浮点，**不要标准化**（标准化会掩盖你在不同录音之间比较的本底噪声电平）。单声道或立体声都可以；立体声文件请在界面中或用 `--channel` 选择话筒声道。不要裁切：RoomScope 会自己找到扫频，扫频之后的静音就是衰减。
7. **延迟无关紧要。** RoomScope 会在录音中任何位置找到扫频，插件延迟补偿和音频接口延迟都无需设置。
8. **可选回送（loopback）。** 在同一遍录音中用第二条轨道录下音频接口的电回送（一路输出用线接回一个空闲输入）。把两条轨道导出为一个双声道文件（`--channel 0 --loopback-channel 1`），或两个文件（`--loopback return.wav`）。

然后分析：

```bash
roomscope analyze --recording "Mic_01.wav" --sweep sweep_44k.wav --out session/
```

或在界面的通用 DAW 模式中选择这些文件。

## Avid Pro Tools

* **采样率：** 创建工程时设定，Session Setup 中可见 [P1，第 1814 页]。按该采样率生成扫频。
* **导入：** File ▸ Import ▸ Audio [P1，第 641 页]。若 Import Audio 对话框的备注栏提示文件采样率与工程不同 [P1，第 643 页]，请按工程采样率重新生成扫频，而不是勾选 *Apply SRC*。
* **时间伸缩：** 保持 Elastic Audio 关闭：轨道的 Elastic Audio 选择器显示 *None – Disable Elastic Audio* [P1，第 1317 页]。请用 File ▸ Import 导入而不要从桌面拖入，或把偏好设置 *Drag and Drop From Desktop Conforms to Session Tempo* 设为 *None*：设为 *All Files* 时，拖入的文件会成为跟随工程速度的 tick 型 Elastic Audio [P1，第 647 页]。
* **录音：** 新建单声道音频轨，输入为话筒，开启录音待命。关闭 TrackInput 时轨道处于 Auto Input 模式，录音期间仍会监听输入 [P1，第 768–769 页]：请把话筒轨推子拉到底（推子不影响录音）。清空扫频轨道和主推子上的插入效果。
* **导出：** 选中录好的片段，在 Clip List 菜单中使用 *Export Clips as Files* [P1，第 649 页]：WAV、单声道、工程采样率与位深（32 位浮点转 24 位会加抖动）。Pro Tools 写出的是 Broadcast WAV，RoomScope 可直接读取。

## Apple Logic Pro 与 GarageBand

* **采样率：** File ▸ Project Settings ▸ Audio ▸ Sample Rate [G1]。Project Settings 的 Assets 页有 *Convert audio file sample rate when importing* [G1]；按工程采样率生成扫频就不需要它。GarageBand for Mac 的指南中没有采样率设置；请按 44.1 kHz 生成扫频（`--sample-rate 44100`），这是 GarageBand iPhone/iPad 指南所写的导入采样率 [G9]。
* **导入：** Logic：File ▸ Import ▸ Audio File，或把 WAV 拖到轨道上 [G2]。GarageBand：把 WAV 拖到轨道上 [G8]。
* **时间伸缩：** Logic 12.3：在片段检查器中取消勾选 *Flex*，并把 *Smart Tempo* 设为 *Off* [G3]（Logic 12.2 及更早版本：*Flex & Follow* = *Off* [G4]；*Smart Tempo* 弹出菜单是 12.3 新增的 [G14]）；在 File ▸ Project Settings ▸ Smart Tempo 中把 *Set Imported Files To* 设为 *Flex Off*，并取消勾选 *Trim start of new regions* [G5]。GarageBand：在音频编辑器中取消勾选 *Follow Tempo and Pitch*，保持 *Enable Flex* 关闭 [G10]。
* **录音：** 单声道音频轨，输入为话筒。Logic 的软件监听默认开启，会播放录音轨的输入 [G6]：请将其关闭（Settings ▸ Audio ▸ General）或把该轨推子拉到底。关闭 Cycle。Logic 的录音文件（CAF、WAVE/BWF 或 AIFF）可以直接分析 [G7]。
* **导出：** Logic：选中录好的片段，File ▸ Export ▸ *1 Region as Audio File*，WAV 或 AIFF，关闭 *Normalize*，勾选 *Bypass Effect Plug-ins* [G11]。GarageBand：静音扫频轨，关闭 *Export projects at full volume*（Settings ▸ Advanced；它会把导出标准化）[G12]，然后用 Share ▸ Export Song to Disk 导出 WAVE 或 AIFF [G13]。该导出会裁掉工程首尾的静音 [G13]；扫频前话筒录到的房间底噪不是数字静音，但请确认导出文件在扫频之前开始。

## Steinberg Cubase 与 Nuendo

* **采样率：** Project ▸ Project Setup [C1]。
* **导入：** File ▸ Import ▸ Audio File [C2]。当 Preferences ▸ Editing ▸ Audio ▸ *On Import Audio Files* 设为 *Open Options Dialog* 时会弹出导入选项，文件采样率或位深不同时会提供 *Convert to Project Settings* [C2]；按工程采样率生成扫频即可避免采样率转换。
* **时间伸缩：** 扫频片段保持 *Musical Mode* 关闭（在 Sample Editor 或 Pool 中；带 ACID 标记的文件会自动开启）[C3]。
* **录音：** 单声道音频轨，输入为话筒。除 *Manual* 外，所有 Auto Monitoring 模式（Preferences ▸ VST）在轨道录音待命时都会打开监听 [C4]：请设为 *Manual*。确认 Control Room 的监听链路上没有插入效果或房间校正插件，或将其旁通 [C5]。
* **导出：** File ▸ Export ▸ Selected Events，*Processing* 选 *Dry* [C6]；或把定位点设在这段录音上，用 File ▸ Export ▸ Audio Mixdown，*Channel Selection* 选 *Single* 并选话筒通道 [C7]。（Audio ▸ Bounce Selection 也可以；它把新文件写入工程的 Audio 文件夹，并应用事件的淡入淡出和音量 [C8]。）

## Fender Studio Pro（原 PreSonus Studio One）

Studio One 自第 8 版（2026 年 1 月）起更名为 Fender Studio Pro，“Song”改称“Session” [S1, S2]；括号中为旧版菜单名。

* **采样率：** Session ▸ Session Setup（v8 之前为 Song ▸ Song Setup）[S2, S6]。创建工程时保持 *Stretch Audio Files to Session Tempo* 关闭 [S9]；打开时新音频轨的默认 Tempo 模式会变成 *Timestretch* [S5]。
* **导入：** 从浏览器把 WAV 拖到音频轨 [S3]。
* **时间伸缩：** 在**轨道**检查器中把轨道的 *Tempo* 模式设为 *Don't Follow*：该轨上的事件“永远不会被自动移动或伸缩” [S4]。在事件检查器中保持 *Speedup* 为 1、*Transpose* 和 *Tune* 为 0，关闭 *Normalize*。事件上的齿轮图标表示开启了时间伸缩、其采样率与工程不同，或改动过移调或微调 [S2]。
* **录音：** 单声道轨，输入为话筒。开启录音时监听会自动打开 [S5]：开启录音待命后请关闭 Monitor 按钮。
* **导出：** 右键录好的事件 ▸ *Export Selection* [S7]；或 Session ▸ Export Stems（v8 之前为 Song ▸ Export Stems），只选话筒轨；分轨包含该轨的插入效果，请先移除或旁通 [S7]。WAV、工程采样率、不标准化。*Use Dithering for Playback and Audio File Export*（Options ▸ Advanced ▸ Audio）默认开启，导出降低位深时会加抖动：请导出 32 位浮点，或关闭该选项 [S8]。

## Ableton Live

* **采样率：** Settings（Windows 为 Options ▸ Settings，macOS 为 Live ▸ Settings）▸ Audio ▸ *In/Out Sample Rate* [L1]。采样率不同的文件会被 Live 实时转换，其 Audio Fact Sheet 称之为“非中性”处理 [L2]：这也是要按 Set 采样率生成扫频的原因之一。
* **导入：** 把 WAV 拖到编曲视图中的音频轨。
* **时间伸缩：** 打开片段，在 Clip View 中**关闭 Warp** [L3]。*Auto-Warp Long Samples*（Settings ▸ Record, Warp & Launch）默认开启 [L4]，所以较长的测试文件若不手动关闭就会被 Warp。
* **录音：** 第二条音频轨，*Audio From* 选话筒输入（单声道），Monitor 设为 *Off*，开启录音待命，在编曲视图中录音 [L5]。
* **导出：** 在编曲视图中选中整段录音，File ▸ Export Audio/Video，*Rendered Track* 选话筒轨，关闭 *Include Return and Main Effects*，WAV 或 AIFF，Set 的采样率，关闭 *Normalize* [L6]。*Create Fades on Clip Edges* 最多加 4 ms 的淡入淡出 [L2]；测试文件首尾都是静音，不会影响扫频。

## Cockos REAPER

* **采样率：** File ▸ Project Settings ▸ 勾选 *Project sample rate* [R1，第 32 页]（不勾选时 REAPER 使用硬件采样率），并在 Preferences ▸ Audio ▸ Device 中勾选 *Request sample rate* 并填入相同的采样率 [R1，第 21 页]。采样率不同的对象会在播放时按工程的 *Playback resample mode* 重采样 [R1，第 32 页]。
* **导入：** Insert ▸ Media file [R1，第 90 页]。
* **时间伸缩：** 在对象属性（F2）中保持 *Playback rate* 为 1.0（*Preserve pitch* 只在速率改变时起作用），并删除伸缩标记 [R1，第 134 页]。工程默认时基为 *Beats (position, length, rate)* [R1，第 33 页]：导入后不要改速度，或在同一对话框中把对象的 *Item timebase* 设为 *Time* [R1，第 134 页]。
* **录音：** 为一条轨道开启录音待命，输入为话筒（单声道），关闭录音监听。
* **导出：** File ▸ Render，*Source* 选 *Selected media items*（或 *Stems (selected tracks)*），WAV、工程采样率；除非在 *Postprocess…* 中设置，否则不做标准化 [R1，第 411–415 页]。默认的对象淡入淡出（Preferences ▸ Project ▸ Item Fade Defaults）落在测试文件首尾的静音上。

## Image-Line FL Studio

* **采样率：** Options ▸ Audio settings（F10）▸ *Sample Rate*，即混音器的播放采样率 [F1]；导出使用该采样率 [F5]。
* **导入：** 把 WAV 拖进 Playlist 作为音频片段。
* **时间伸缩：** 在片段的通道设置中保持 *Time* 旋钮为 *(none)*，这是把采样拖到 Playlist 时的默认值；这样无论工程速度如何，片段都保持原有音高和时长 [F2]。如果片段仍被伸缩，请关闭 General settings ▸ *Read sample tempo information*，它会应用 WAV 文件中保存的速度信息 [F6]。默认的去咔嗒处理会加 10 ms 淡出 [F2]，落在测试文件末尾的静音上。
* **回放链路：** 自 FL Studio 20.7 起默认模板为“Basic 808 with limiter” [F3]；测量时请旁通 Master 插槽上的限幅器。
* **录音：** 把话筒输入路由到一个空闲的 Mixer 插槽。默认情况下实时输入会经 Master 回到输出 [F4]，因此请把该插槽的 *Monitor external input* 设为 *Off*（否则可能回授），并关闭默认开启、会叠加多次录音的 *Loop record* [F4]。为该插槽开启录音待命，把音频录进 Playlist。
* **导出：** File ▸ Export ▸ Wave file，勾选 *Split mixer tracks*，使用话筒插槽对应的文件（被静音的轨道会被跳过）[F5]。WAV、工程采样率。

## Bitwig Studio

* **采样率：** Dashboard ▸ Settings ▸ Audio [B1]。
* **导入：** 把 WAV 拖到编排器中的音频轨。在 Dashboard ▸ Settings ▸ Behavior ▸ Audio Import 中把 *Stretch behavior* 设为 *Original speed [Raw]*，*Start clip from* 设为 *Sample Start* [B1]。
* **时间伸缩：** 在检查器中把片段的 *Stretch* ▸ *Mode* 设为 *Raw*，它忽略伸缩数据、按原速播放 [B2]。（没有 *Off* 模式。）
* **录音：** 音频轨，输入为话筒，关闭监听。
* **导出：** File ▸ Export Audio，只选话筒轨，WAV，采样率选 *Current*（不转换）[B3]。

## MOTU Digital Performer

菜单名称取自 Digital Performer 12 用户指南 [M1]；Digital Performer 11 指南描述的是相同的命令 [M2]。

* **采样率：** 控制面板中的 *Sample Rate* 设置工程采样率 [M1，第 222 页]；音频接口在 Setup ▸ Configure Audio System ▸ Configure Hardware Driver 中选择 [M1，第 260 页]。按该采样率生成扫频，之后不要再改工程采样率。录音前在 Preferences ▸ Audio Files 中选择 Broadcast WAVE 以及 24 位或 32 位浮点；这些设置作用于新录制的文件 [M1，第 84 页]。
* **导入：** File ▸ Import Audio，或把 WAV 拖到单声道音频轨上 [M1，第 40–42 页]。DP 不会以错误的速度播放采样率不同的文件：该片段在 Soundbites 窗口中带有“X”且不能播放 [M1，第 43、50 页]；或者在开启 *Enable Automatic Conversions* 且 *Convert sample rate* 设为 *On import*（Preferences ▸ Automatic Conversions）时，DP 会在导入时转换 [M1，第 97 页]。按工程采样率生成扫频即可避免这两种情况。片段增益保持 0 dB，不要添加片段音量自动化 [M1，第 400 页]。
* **时间伸缩：** 在扫频轨和话筒轨的 Track Settings 菜单中取消勾选 *Stretch*；取消后不会自动伸缩 [M1，第 170 页]（Preferences ▸ Pitch and Stretch 为新轨道设置此项 [M1，第 104 页]）。带有内嵌速度信息的 WAV 会适配序列速度 [M1，第 44 页]，录下的 take 会带着录音时的速度映射 [M1，第 713 页]，所以录音后不要改速度，也不要使用 Audio ▸ Soundbite Tempo ▸ *Adjust Soundbites to Sequence Tempo*；把片段的 *Time Compress/Expand* 设为 *Don't Time Scale* 可让该命令不作用于它 [M1，第 399、717 页]。
* **录音：** Project ▸ Add Track ▸ 单声道音频轨 [M1，第 140 页]，输入为话筒，开启录音待命 [M1，第 260 页]。开启录音待命会打开输入监听，与监听按钮显示无关 [M1，第 265 页]：请把 Studio ▸ Audio Patch Thru 设为 *Off* [M1，第 266 页]。保持 *Memory Cycle* 和 *Overdub* 关闭，只录一遍 [M1，第 273 页]。旁通扫频轨和主输出上的插入效果。
* **导出：** take 是工程 *Audio Files* 文件夹中以轨道名和 take 编号命名的文件 [M1，第 261 页]；直接把它载入 RoomScope：它就是录音本身，不含推子、插入效果或自动化。或者选中从扫频之前到衰减结束的这段录音，用 File ▸ Bounce to Disk [M1，第 1017 页]，*Source* 选话筒轨 [M1，第 1021 页]，*Channels* 选 *Match Track Format*（单声道轨得到单声道文件），*Sample Format* 选 *Project Default*、24 位或 32 位浮点 [M1，第 1020–1021 页]。导出会包含该轨的音量自动化、静音/独奏状态和启用的插入效果 [M1，第 1017–1018 页]；其设置中没有采样率、标准化或抖动选项 [M1，第 1018–1021 页]。

## Audacity

* **采样率：** Audio Setup ▸ Audio Settings 中 *Quality* 部分的 *Project Sample Rate* [A1]。
* **导入：** File ▸ Import ▸ Audio [A2]。
* **录音：** 在 Transport ▸ Transport Options 中打开 *Hear other tracks during recording*，关闭 *Enable audible input monitoring*（旧版本中分别叫 *Overdub* 和 *Software Playthrough*）[A3]。把 Audio Setup ▸ Recording Channels 设为 1（单声道），光标放在开头，使用 **Record New Track**（Shift+R）：普通 Record 会从所选轨道末尾开始录，扫频已经播完 [A4]。
* **导出：** 选中录音轨，File ▸ Export Audio…，*Export Range* 选 *Current Selection*，WAV，*Signed 24-bit PCM* 或 *32-bit float* [A5]。（Audacity 3.4 已移除 *Export Selected Audio* [A6]。）

## 其他 DAW

对于上面没有列出的 DAW（v8 之前的 Studio One、Cakewalk by BandLab 或 Cakewalk Sonar、Ardour、Harrison Mixbus、Tracktion Waveform、Reason、LUNA 等），请在其手册中逐条查找下面各点。每一条都来自[每个 DAW 都必须做到](#每个-daw-都必须做到)。

1. **先定采样率。** 导入任何东西之前先设好工程采样率，并按该采样率生成扫频。有些 DAW 会不经转换、以错误速度播放采样率不同的文件（Pro Tools [P1，第 636 页]、Logic [G1]）；另一些会在导入时转换（Cakewalk [CW1]、Ardour [AR2]），这会把 DAW 的重采样器带进测量。导入后在文件列表或素材池中检查片段的采样率。
2. **导入到时间线上的普通音频轨**，不要导入采样器、片段启动器或循环浏览器。关闭扫频片段和话筒轨上的所有速度功能（warp、flex、elastic、musical mode、follow tempo、stretch to tempo、导入时的速度检测），之后也不要改速度。片段长度必须与 WAV 文件完全一致。
3. **片段保持原样：** 不要片段增益包络、淡入淡出、交叉淡化、标准化、移调或微调，也不要自动裁切到第一个瞬态。
4. **干净的回放链路：** 旁通扫频轨、其总线和主输出上的插件（默认模板可能带限幅器）以及任何房间校正插件；把扫频路由到一只扬声器。
5. **单声道录一遍：** 没有插件的单声道轨，关闭输入监听，关闭循环 / 循环录音 / take 录音，在扫频前开始、在衰减结束后停止。
6. **导出这段录音，而不是混音：** 最好直接用工程音频文件夹中的录音文件本身。否则以干声导出该片段或轨道，采用工程采样率、24 位或 32 位浮点 WAV、AIFF 或 FLAC，不标准化、不加抖动、不降低位深、不经过主总线处理，也不裁掉静音或尾音。

**Ardour。** Session ▸ Import 打开 *Add Existing Media* 对话框 [AR1]；采样率与工程不同的文件显示为红色，表示“导入前必须重采样” [AR2]。请改为按工程采样率生成扫频。编辑器中的区域只有在使用 Stretch Mode 工具时才会被伸缩 [AR3]；Cue 槽中的片段有自己的伸缩模式 [AR4]，所以请把扫频放在编辑器时间线上。

**Cakewalk by BandLab / Cakewalk Sonar。** File ▸ Import Audio 会把采样率不同的文件转换为工程采样率；*Bit Depth* 保持默认的 *Original* [CW1, CW2]。开启伸缩的片段会跟随工程速度，未开启的不会；请为扫频关闭 AudioSnap 的 *Follow Project Tempo* 和 Groove Clip 的 *Stretch to Tempo* 选项 [CW3]。

## 报告提示有问题时

下表引用的是英文原文。界面语言为简体中文时，部分提示会以中文显示，措辞与下表的英文不完全对应；核心诊断保持英文。

| RoomScope 提示 | DAW 里发生了什么 | 解决办法 |
| --- | --- | --- |
| *“a file generated at 48000 Hz was played at 44100 Hz”* | 工程采样率与扫频不同，且播放时未转换 | 按工程采样率生成扫频 |
| *“the DAW time-stretched it”* | 扫频片段开启了 Warp / Flex / Follow Tempo / 伸缩，或导入后改了速度 | 关闭该片段的时间伸缩 |
| *“the recording starts ... after the sweep began”* | 录音开始得太晚，或导出时被裁切 | 在扫频开始前录音；完整导出片段 |
| *“harmonic ... was folded back”* | 回放链路上有限幅器、削波器或过载的总线 | 旁通主输出和轨道插件；降低扫频轨电平 |
| *“flat-topped peaks ... probable clipping”* | 话放增益过高 | 降低输入增益 |
| *“the recording contains N sweep passes”* | 循环录音，或扫频放了两次 | 只录一遍 |
| *“recording is silent”* | 输入选错或轨道被静音 | 检查输入和导出的是哪条轨 |
| *“the recording has no background noise at all”*（中文界面：“这段录音完全没有背景噪声”；RT60 只有百分之几秒，没有反射） | 导出了测试信号轨而不是话筒轨，或话筒轨上有门限 / 降噪 | 以干声导出话筒轨 |
| *“direct-sound detection confidence is low”* 且不属于以上情况 | 参考扫频不对、低于上述离散范围的小幅时间伸缩或忘了关 Warp / Flex、房间很吵，或扬声器严重失真 | 使用实际播放的扫频；检查伸缩；降低回放电平 |

## 来源

以上菜单名称和默认值读自以下页面（2026-09）；其中任何一步都还没有在 DAW 中配合 RoomScope 实际运行过。条目保留原文：

* [P1] Avid, Pro Tools Reference Guide 2026.4 — https://resources.avid.com/SupportFiles/PT/Pro_Tools_Reference_Guide_2026.4.pdf
* [G1] Apple, Logic Pro User Guide, Set the project sample rate — https://support.apple.com/guide/logicpro/set-the-project-sample-rate-lgcpce0958b8/mac
* [G2] Apple, Logic Pro User Guide, Add and delete audio files — https://support.apple.com/guide/logicpro/add-and-delete-audio-files-lgcp1bb0ad7d/mac
* [G3] Apple, Logic Pro User Guide, Choose the Smart Tempo setting — https://support.apple.com/guide/logicpro/choose-the-smart-tempo-setting-lgcpb7abb9cc/mac
* [G4] Apple, Logic Pro 12.2 User Guide, Flex & Follow — https://support.apple.com/guide/logicpro/lgcpb7abb9cc/12.2/mac/15.6
* [G5] Apple, Logic Pro User Guide, Smart Tempo project settings — https://support.apple.com/guide/logicpro/smart-tempo-project-settings-lgcp6ad7156e/mac
* [G6] Apple, Logic Pro User Guide, General settings (software monitoring) — https://support.apple.com/guide/logicpro/general-settings-lgcp0ed343a9/mac
* [G7] Apple, Logic Pro User Guide, Recording settings — https://support.apple.com/guide/logicpro/recording-settings-lgcp411dd5c8/mac
* [G8] Apple, GarageBand for Mac User Guide, Import audio and MIDI files — https://support.apple.com/guide/garageband/import-audio-and-midi-files-gbndd01649ed/mac
* [G9] Apple, GarageBand for iPhone User Guide (imports converted to 44.1 kHz) — https://support.apple.com/guide/garageband-iphone/
* [G10] Apple, GarageBand for Mac User Guide, Intro to the Audio Editor — https://support.apple.com/guide/garageband/intro-to-the-audio-editor-gbndca7725e3/mac
* [G11] Apple, Logic Pro User Guide, Export regions as audio files — https://support.apple.com/guide/logicpro/export-regions-as-audio-files-lgcp8e5ce2d3/mac
* [G12] Apple, GarageBand for Mac User Guide, Change Advanced settings — https://support.apple.com/guide/garageband/change-advanced-settings-gbnded6e79bc/mac
* [G13] Apple, GarageBand for Mac User Guide, Export songs to disk — https://support.apple.com/guide/garageband/export-songs-to-disk-or-icloud-gbnd7cbf5ed9/mac
* [G14] Apple, Logic Pro for Mac release notes (12.3: Smart Tempo pop-up) — https://support.apple.com/en-us/109503
* [C1]–[C8] Steinberg, Cubase Pro / Nuendo 15 help (steinberg.help): Project Setup; Import Options dialog (`importing_audio_and_midi_open_options_dialog_r`); Musical Mode; Auto Monitoring (Preferences ▸ VST); Control Room; Export Selected Events (`parts_and_events_export_selected_events_r`); Export Audio Mixdown options (`export_audio_mixdown_options_r`); Bounce Selection (`parts_and_events_from_events_new_files_creating_t`) — https://steinberg.help/r/cubase-pro/15.0/en/
* [S1] synthanatomy.com, report on the Fender Studio Pro 8 release (January 2026; third-party)
* [S2]–[S7] Fender Studio Pro 8.1 manual: Events; The Browser ▸ Files tab; Timestretching and Track/Event Inspectors; Audio Tracks; Session Setup; Exporting Audio and MIDI Files — https://fenderstudiopromanual.fender.com/en/Content/ (Studio One 5 Reference Manual for pre-v8 names)
* [S8] Fender Studio Pro manual, Advanced Options — https://fenderstudiopromanual.fender.com/en/Content/Setup_Topics/Advanced_Options.htm
* [S9] Fender Studio Pro manual, Creating a New Session — https://fenderstudiopromanual.fender.com/en/Content/Setup_Topics/Creating_a_New_Session.htm

* [L1] Ableton, Live 12 manual, First Steps — https://www.ableton.com/en/live-manual/12/first-steps/
* [L2] Ableton, Live 12 manual, Audio Fact Sheet — https://www.ableton.com/en/live-manual/12/audio-fact-sheet/
* [L3] Ableton, Live 12 manual, Clip View — https://www.ableton.com/en/live-manual/12/clip-view/
* [L4] Ableton, Live 12 manual, Audio Clips, Tempo, and Warping — https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/
* [L5] Ableton, Live 12 manual, Routing and I/O — https://www.ableton.com/en/live-manual/12/routing-and-i-o/
* [L6] Ableton, Live 12 manual, Managing Files and Sets — https://www.ableton.com/en/live-manual/12/managing-files-and-sets/
* [R1] Cockos, REAPER User Guide 7.80 — https://www.reaper.fm/userguide/ReaperUserGuide780.pdf
* [F1] Image-Line, FL Studio manual, Audio Settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_audio.htm
* [F2] Image-Line, FL Studio manual, Sampler channel settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/chansettings_sampler.htm
* [F3] Image-Line, FL Studio 20.7 release notes — https://www.image-line.com/fl-studio-news/fl-studio-207-released
* [F4] Image-Line, FL Studio manual, Recording audio — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/recording_audio.htm
* [F5] Image-Line, FL Studio manual, Export — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/fformats_save_export.htm
* [F6] Image-Line, FL Studio manual, General Settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_general.htm
* [B1] Bitwig Studio user guide, The Dashboard — https://www.bitwig.com/userguide/latest/the_dashboard/
* [B2] Bitwig Studio user guide, Inspecting audio clips — https://www.bitwig.com/userguide/latest/inspecting_audio_clips/
* [B3] Bitwig Studio user guide, Exporting audio — https://www.bitwig.com/userguide/latest/exporting_audio/
* [A1] Audacity manual, Audio Settings Preferences — https://manual.audacityteam.org/man/audio_settings_preferences.html
* [A2] Audacity manual, File Menu — https://manual.audacityteam.org/man/file_menu.html
* [A3] Audacity manual, Transport Options — https://manual.audacityteam.org/man/transport_menu_transport_options.html
* [A4] Audacity manual, Recording — https://manual.audacityteam.org/man/transport_menu_recording.html
* [A5] Audacity manual, Export dialog — https://manual.audacityteam.org/man/file_export_dialog.html
* [A6] Audacity forum, "What happened to Export Selected Audio?" — https://forum.audacityteam.org/t/what-happened-to-export-selected-audio/88742 (forum)
* [M1] MOTU, Digital Performer 12 User Guide (2026) — https://cdn-data.motu.com/manuals/software/dp/v1200/Digital%20Performer%20User%20Guide.pdf
* [M2] MOTU, Digital Performer 11 User Guide — https://cdn-data.motu.com/manuals/software/dp/v11/Digital+Performer+User+Guide.pdf
* [AR1] Ardour manual, Adding Pre-existing Material — https://manual.ardour.org/adding-pre-existing-material/
* [AR2] Ardour manual, Import Dialog — https://manual.ardour.org/adding-pre-existing-material/import-dialog/
* [AR3] Ardour manual, Stretching — https://manual.ardour.org/editing/editing-regions-and-selections/stretching/
* [AR4] Ardour manual, Clip stretch options (Cues) — https://manual.ardour.org/cue/setting-up-cues/clip-stretch-options/
* [CW1] Cakewalk documentation, Import Audio dialog — http://legacy.cakewalk.com/Documentation?product=Cakewalk&language=3&help=0x200FB
* [CW2] Cakewalk Sonar documentation, Import Audio dialog — https://legacy.cakewalk.com/Documentation?product=CakewalkSonar&language=3&help=0x200FB
* [CW3] Cakewalk documentation, How tempo changes affect audio clips — https://legacy.cakewalk.com/Documentation?product=Cakewalk&language=3&help=Tempo.02.html
