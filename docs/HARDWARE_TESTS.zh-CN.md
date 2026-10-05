# 硬件测试矩阵

[English](HARDWARE_TESTS.md) | **简体中文**

本文是 [HARDWARE_TESTS.md](HARDWARE_TESTS.md) 的简体中文翻译。测试结果由维护者填入英文版的表格；本页表格随翻译同步，两者不一致时以英文版为准。

依据 ARCHITECTURE_V1.md §7.3：1.0 之前（M10）每个平台至少执行一次，并在此记录日期、ReverbScope 版本和构建提交、操作系统以及音频接口。

下面没有任何一项在未经真实硬件运行的情况下被标为 PASS。真实硬件指：一台实体电脑、一个实体音频接口及其实际驱动，检查需要时进行真实的播放和录制。演示模式、`fake` 后端、合成测试与脚本化 PortAudio 测试以及 CI 运行器都不算数。表格是有意留空的：还没有任何检查在真实硬件上运行过。

**提交结果。** 请提交 [音频接口测试报告（中文表单）](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware-zh-CN.yml)（英文：[Audio interface test report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware.yml)）或 [DAW 兼容性报告（中文表单）](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw-zh-CN.yml)（英文：[DAW compatibility report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw.yml)）issue。两者都要求附上环境报告（**帮助 → 用于问题报告的环境报告**，或 `reverbscope doctor`；音频接口报告需要带探测采样率的版本，即 `reverbscope doctor --probe`），其中写明版本、构建提交、操作系统、音频系统（主机 API）和设备。音频接口报告要求对下表每一行回答 Pass（通过）/ Fail（失败）/ Not run（未运行）。维护者会把结果连同 issue 链接抄进下表对应的单元格。

| 检查项 | macOS | Windows | Linux |
| --- | --- | --- | --- |
| 设备枚举 | | | |
| 采样率协商 44.1 kHz | | | |
| 采样率协商 48 kHz | | | |
| 采样率协商 96 kHz | | | |
| 1–2 以外的声道映射 | | | |
| 回送（loopback）录制 | | | |
| 播放中停止（一个回调周期内输出静音） | | | |
| 完整测量且日志中没有缓冲区欠载/溢出（`reverbscope -v measure`） | | | |
| 测量中拔掉设备会报告为失败，而不是保存为录音 | | | |
| 完整的独立模式测量 | | | |
| 同一信号经过一个 DAW（通用 DAW 模式） | | | |

单元格记录格式为 `PASS YYYY-MM-DD, ReverbScope x.y.z (commit), <OS version>, <interface and driver>, #issue` 或 `FAIL ... #issue`。不要根据 fake 后端、CI 运行器或测试结果填写单元格。

## DAW 矩阵

每个 DAW 做一次通用 DAW 模式测量，严格按照 [user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md)（英文版 [user-guide/daw-setup.md](user-guide/daw-setup.md)）操作：按工程采样率生成扫频，用文中列出的菜单录音和导出，分析结果的 `direct_sound_confidence` 为 high（高）。一个单元格同时也检验说明对该 DAW 版本是否正确；不正确时，请在同一个 pull request 中修正指南。每个 DAW 再做两项反向检查，确认诊断有效：一是在 44.1 kHz 工程中使用 48 kHz 扫频，并关闭 DAW 的导入转换（预期出现采样率提示；在播放时重采样的 DAW，如 Live 或 REAPER，应当给出有效结果，而 Digital Performer 会拒绝播放该文件：请记录实际发生了什么）；二是对会做时间伸缩的 DAW，把片段伸缩（例如到 97 %）或在导入后改变速度（预期出现时间伸缩提示）。

| DAW（版本） | macOS | Windows | Linux | 采样率提示 | 时间伸缩提示 |
| --- | --- | --- | --- | --- | --- |
| Pro Tools | | | 不适用 | | |
| Logic Pro | | 不适用 | 不适用 | | |
| GarageBand | | 不适用 | 不适用 | | |
| Cubase / Nuendo | | | 不适用 | | |
| Fender Studio Pro (Studio One) | | | | | |
| Ableton Live | | | 不适用 | | |
| REAPER | | | | | |
| FL Studio | | | 不适用 | | |
| Bitwig Studio | | | | | |
| Digital Performer | | | 不适用 | | |
| Audacity | | | | | 不适用 |

自动化测试能说明的是：`tests/integration/test_daw_exports.py` 分析以 Broadcast WAV（带 `bext`、`iXML` 和 `JUNK` 块）、WAVE_FORMAT_EXTENSIBLE、RF64、Wave64、AIFF、CAF 和 FLAC 写出的同一段录音，位深为 16 / 24 / 32 位 PCM 和 32 位浮点，还包括单声道话筒的立体声导出；`tests/integration/test_playback_speed.py` 把合成扫频在 44.1 / 88.2 / 96 kHz 下未经转换播放，以及做 ±3 % 的时间伸缩，并检查诊断结果。这些测试都没有运行 DAW，所以都不能填写上表的任何单元格。

自动化测试能说明和不能说明的：`tests/unit/test_audio_backend.py` 运行合成的 `fake` 后端，`tests/unit/test_portaudio_backend.py` 通过一个脚本化的 `sounddevice` 替身驱动 `PortAudioBackend` 的真实回调代码（等待线程中的进度、回调异常、流提前结束、停止、状态标志）。两者都没有接触 PortAudio 或音频接口，所以都不能填写上表的单元格；尤其是停止测试，其取消标志是测试自己设置的（#13）。

## 测试者分步说明

一台电脑上测一个音频接口大约需要一小时；只做其中一部分也有帮助。请如实报告发生的情况，包括失败和跳过的检查：附有原因的“Fail”或“Not run”与“Pass”同样有用。

**开始之前**

1. 把监听音箱或耳机的音量**调低**。测试信号是 20 Hz 到 20 kHz 的正弦扫频；从低音量开始，逐步调高到话筒处能清楚听到扫频为止，绝不要很响。高于 −12 dBFS 的电平，ReverbScope 会拒绝播放，除非你确认。
2. 从最新的 Release 安装 ReverbScope（各系统的步骤见[用户指南](user-guide/zh-CN.md#安装)）。安装包还没有签名：在 macOS 上先打开一次，然后在 **系统设置 ▸ 隐私与安全性 ▸ 仍要打开** 中放行；在 Windows 上，于 SmartScreen 中点 **更多信息 ▸ 仍要运行**；在 Linux 上先安装 `libportaudio2`。在 macOS 上，系统询问时请允许麦克风访问（**系统设置 ▸ 隐私与安全性 ▸ 麦克风**）。
3. 连接音频接口，按你平时的用法在它自己的控制面板中设置好，并记下驱动版本和在那里设置的缓冲区大小。
4. 先点 **探测采样率**，再复制 **帮助 ▸ 用于问题报告的环境报告** 的内容（或运行 `reverbscope doctor --probe`）。这一步不会播放任何声音。把它粘贴到报告中；其中写明版本、构建提交、操作系统、音频系统和设备，你的主目录显示为 `~`。

**音频接口检查**（表单中每一行回答一次）

| 行 | 怎么做 | 通过条件 |
| --- | --- | --- |
| 设备列表 | 打开独立模式（或运行 `reverbscope devices`） | 音频接口出现在列表中，输入和输出数量正确 |
| 44.1 / 48 / 96 kHz 下的完整测量 | 在独立模式中把该音频接口选为输入和输出，设置采样率，点 **开始测量**；对音频接口提供的每个采样率重复一次 | 能打开结果，直达声置信度不是“低”，也没有警告说采样率不受支持或录音有丢帧 |
| 1–2 以外的声道 | 选择声道 2 以上的输入或输出 | 扫频从你选的声道输出，并从你选的声道录下 |
| 回送录制 | 用线把一路输出接回一路输入，并把它选为回送声道 | 结果中说明回送已补偿 |
| 播放中停止 | 扫频播放时点 **停止** | 声音立即停止，没有残留的持续音，不保存任何结果 |
| 没有缓冲区欠载/溢出 | 用你平时的设置做一次完整测量 | 结果和 `reverbscope.log` 中都没有 “buffer problem(s) … may contain dropouts” 警告（中文界面中的相应提示以“音频设备在本次测量中报告了丢失或延迟的缓冲区”开头） |
| 拔掉音频接口 | 先调低监听；在测量过程中拔掉线缆 | ReverbScope 报告错误且不保存任何内容；不会卡死或崩溃 |
| 完整的独立模式测量 | 在房间里使用话筒和扬声器 | 得到一个你能读懂的结果 |
| 同一信号经过一个 DAW | 用同一个音频接口进行通用 DAW 模式测量 | 见下面的 DAW 步骤 |

缓冲区与延迟：ReverbScope 使用音频接口驱动中的设置。如果某次测量报告了丢帧，请在音频接口的控制面板中调大缓冲区，关闭其他音频程序，然后再试；并在报告中写明这两项设置。开发者版（从源码安装，或打开 **文件 ▸ 设置 ▸ 显示开发者工具** 并重启）还提供 **延迟：低 / 高**，以及按系统提供的 WASAPI 独占模式（Windows）或让 ReverbScope 设置设备采样率（macOS）；如果改动了这些选项，请记录下来。安装包不使用 ASIO。

**DAW 检查**（一个 DAW，一次测量）

1. 严格按照 [user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md) 中你所用 DAW 的说明操作；记下你的版本中与说明不同的菜单。
2. 按工程采样率生成扫频，经扬声器播放，录下话筒，导出录音，然后在通用 DAW 模式中分析。
3. 直达声置信度为“高”，且没有出现采样率或时间伸缩提示，即为通过。之后如果条件允许，再做上面 DAW 矩阵中的两项反向检查：ReverbScope 能指出问题所在，即为通过。

**需要提交什么**

* 表单：[音频接口测试报告（中文表单）](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware-zh-CN.yml)或 [DAW 兼容性报告（中文表单）](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw-zh-CN.yml)；英文表单为 [audio interface test report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware.yml) 和 [DAW compatibility report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw.yml)。
* 环境报告（上面第 4 步）。
* 任何失败都请附上数据文件夹（`~/.reverbscope/`，或 **环境报告 ▸ 打开数据文件夹**）中的 `reverbscope.log`；如果保存了结果，再附上用 `reverbscope session bundle <session folder> --no-audio` 生成的会话打包文件（只有在你愿意分享房间录音时才去掉 `--no-audio`）。
