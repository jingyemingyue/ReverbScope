# 音频设备与主机 API

[English](AUDIO_DEVICES.md) | **简体中文**

> 本文是 [AUDIO_DEVICES.md](AUDIO_DEVICES.md) 的简体中文翻译；两者不一致时以英文版为准。

最后核对：2026-09-24。本文针对**独立模式**：RoomScope 通过 python-sounddevice
0.5.6 调用 PortAudio 自己播放并录音。sounddevice 的 Windows 和 macOS wheel
内置 PortAudio v19.7.0；在 Linux 上它加载发行版的 `libportaudio2` [14][15]。
文中 PortAudio 的行为依据 v19.7.0 源码 [9]–[12]。通用 DAW 模式下设备链路由 DAW
掌管，但同样的规则适用（[user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md)）。

## 1. 为什么设备链路很重要

扫频测量把扬声器、房间和话筒当作线性、时不变系统（ISO 18233 对这两点都提出了
要求 [8]），并用生成的扫频信号对录音反卷积。设备链路额外加入的任何东西，都会被
当作房间的一部分测出来。

* **同一个采样时钟。** 播放和录音应共用一个时钟，或使用相互同步的时钟 [7]。两个
  时钟会相互漂移（第 3 节）。
* **不做采样率转换。** 转换器就是一个带延迟的低通滤波器；例如 PipeWire 就在文档
  中给出了其重采样器的截止频率、窗函数和延迟 [35]。以 48 kHz 运行的混音器无法
  传送 96 kHz 扫频中 24 kHz 以上的部分。跟随另一个时钟的转换器（漂移校正、自适应
  重采样）会在录音过程中改变转换比：这是一种时变，扫频对它的容忍度远高于 MLS，
  但并非完全免疫 [2, §2.4][5]。
* **不做处理。** 操作系统加载的均衡器、自动增益控制、回声消除及其他效果 [21]，
  以及混入输出的其他应用的声音 [18]，都会进入结果。限幅器或 AGC 是非线性环节，
  而扫频无法把所有失真伪影都移出响应的因果部分 [3]。
* **电平不被改变。** 任何环节都不应缩放信号。扫频的峰值因数为 3.01 dB，可以接近
  满刻度运行，而 MLS 需要 5–8 dB 余量 [2, §2.2]；为保护扬声器，RoomScope 仍从
  −20 dBFS 起步（`audio/backend.py`）。
* **延迟稳定、没有丢帧。** 反卷积得到的时间原点包含往返延迟；只有回送（loopback）能给出
  电气时间零点（[MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md)
  §2a）。输出缓冲区欠载会插入空隙，输入缓冲区溢出会丢弃样本 [9]；RoomScope 会统计这些标志并
  随测量保存：它们出现在结果的警告中，并生成一条“请重新测量”的提示
  （`audio/portaudio.py`、`AudioSignal.device_warnings`）。在真实音频接口证明某些主机 API
  是否会误报之前，这类测量仍会被分析，而不是直接拒绝。

## 2. 各平台的主机 API

每个 PortAudio 设备只属于一种主机 API [9][13]，因此一个音频接口可经由几种主机 API 访问，
就会出现几次（`roomscope devices` 在方括号中显示主机 API）。排名 1 为最佳。“默认延迟”是 PortAudio 的默认建议值（低 / 高），
不是实测的往返延迟。

### Windows

| 排名 | 主机 API（PortAudio 名称） | 采样率转换 | 混音 / 处理 | 默认延迟 |
| --- | --- | --- | --- | --- |
| 1 | `Windows WASAPI`，独占 | 无：硬件必须支持该格式 [16] | 无：绕过音频引擎 [23] | 设备最小 / 默认周期 [10] |
| 2 | `ASIO` | 驱动支持的采样率（`ASIOCanSampleRate`）[12] | 厂商驱动，绕过引擎 [23] | 驱动首选 / 最大缓冲 [12] |
| 3 | `Windows WDM-KS` | 无：驱动 pin 必须支持该采样率 [12] | 位于系统混音器之下；独占设备 [12] | 10 / 40 ms（WaveRT），10 / 85 ms（WaveCyclic）[12] |
| 4 | `Windows WASAPI`，共享 | 除非设置 `auto_convert`，PortAudio 只接受共享模式采样率 [10] | 音频引擎：混音和 APO [18][21] | 同独占；引擎缓冲默认 10 ms [23] |
| 5 | `Windows DirectSound` | 自动转换 [16] | 音频引擎 [19]；已弃用的 API [22] | 120 / 240 ms [12] |
| 6 | `MME` | 自动转换 [16] | 音频引擎 [19] | 90 / 180 ms [12] |

* **WASAPI 共享模式**是 RoomScope 的默认打开方式（不带主机专用设置，
  `audio/portaudio.py`）；`roomscope measure --wasapi-exclusive` 改用独占模式（见下）。引擎以“声音”控制面板中选定的共享模式格式运行（设备 ▸
  属性 ▸ 高级 ▸ *默认格式*）[16]；PortAudio 把该采样率报告为默认值，拒绝其他采样率
  [10]。`WasapiSettings(auto_convert=True)` 会插入声道矩阵和采样率转换器
  （`AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`）[14][20]；因此 RoomScope 不提供该选项。把默认格式设为
  测量采样率，并关闭增强（“增强”选项卡或“高级”选项卡）[24]。端点效果即使对 raw
  流也会生效 [21]，编解码器或 DSP 也可能在硬件中处理信号 [22]。
* **WASAPI 独占模式**（`WasapiSettings(exclusive=True)` [14]；RoomScope：`--wasapi-exclusive`）需要勾选*允许应用程序
  独占控制该设备*（默认开启），并会让其他应用静音 [17]；PortAudio 给出的数字约为
  3 ms，共享模式不低于 20 ms [10]。
* **ASIO** DLL 因许可原因已从 RoomScope 安装包中移除（[DEPENDENCIES.md](DEPENDENCIES.md)
  §3）；sounddevice 只有在设置 `SD_ENABLE_ASIO` 时才加载其 ASIO DLL [14]。一台 ASIO
  设备同时负责两个方向 [12]。
* **麦克风隐私：** 设置 ▸ 隐私和安全性 ▸ 麦克风 ▸ 打开*麦克风访问权限*和*允许桌面
  应用访问你的麦克风* [25]。

### macOS

Core Audio 是唯一的主机 API（排名 1）。使用一块设为测量采样率的音频接口，或使用聚合
设备（第 3 节）。

* **标称采样率。** 设备以一个标称采样率运行（`kAudioDevicePropertyNominalSampleRate`）
  [29]，在“音频 MIDI 设置”▸ *格式* 中设定 [26]；PortAudio 把它报告为默认采样率 [11]。
* **转换。** PortAudio 默认“友好共享”（play nice）：由 AUHAL 转换输出、由
  AudioConverter 转换输入，采用最高质量，而不改动设备 [11]。
  `CoreAudioSettings(change_device_parameters=True)` 允许 PortAudio 设置标称采样率
  （可能干扰正在使用该设备的其他程序，即使只是查询）；再加
  `fail_if_conversion_required=True` 则拒绝任何转换 [11][14]。RoomScope 默认不传
  CoreAudioSettings：请在“音频 MIDI 设置”中设定采样率；界面会标出与请求不一致的
  设备采样率（`ui/pages.py`）。`roomscope measure --coreaudio-set-rate` 会传入
  `change_device_parameters=True, fail_if_conversion_required=True`，测量要么以请求的采样率运行，要么失败，而不会转换。
* **延迟。** 默认低延迟 = 设备固定延迟 + 64 帧；高延迟 = 固定延迟 + 当前缓冲大小；
  读不到时为 10 / 100 ms [11]。
* **麦克风权限：** 系统设置 ▸ 隐私与安全性 ▸ 麦克风 [30]；打包的应用必须声明
  `NSMicrophoneUsageDescription` [31]。没有权限时 RoomScope 报告
  *“recording is silent”*（[用户指南](user-guide/zh-CN.md)）。

### Linux

| 排名 | 主机 API / 设备 | 采样率转换 | 混音 / 处理 | 默认延迟 |
| --- | --- | --- | --- | --- |
| 1 | `ALSA`，`hw:X,Y` | 无：“raw communication without any conversions” [32] | 无 [32] | (512−128)/fs / (2048−512)/fs：48 kHz 时为 8 / 32 ms（若硬件允许）[12] |
| 2 | `JACK Audio Connection Kit` | 无：只有一个服务器采样率，其他采样率被拒绝 [12][37] | JACK 连接图 | 端口延迟 ÷ 采样率 [12] |
| 3 | `ALSA`，`plughw:` | 仅当采样率、格式或声道数不是原生值时 [32] | 无 | 同 `hw:` |
| 4 | `ALSA`，`default` / `dmix` / `pulse` / `pipewire` | 有：dmix 默认 48 kHz [33]；PipeWire 重采样到其图采样率，默认 48 kHz [34][35]；PulseAudio 以默认或备用采样率运行 [36] | dmix 混合多路流 [32]；PipeWire 的 adapter 转换格式、采样率和声道布局 [35] | 由服务器决定 |
| 5 | `OSS` | 由驱动决定；PortAudio 接受 1 % 以内的采样率 [12] | 如使用 ALSA 的 OSS 仿真 [38] | 未评估 |

* PortAudio 把 ALSA 硬件命名为 `card: device (hw:X,Y)`，同时也列出插件和服务器
  PCM（`default`、`pulse`、`pipewire` 等）；设置 `PA_ALSA_PLUGHW=1` 会让它打开
  `plughw:` 而不是 `hw:` [12]。
* **PipeWire** 在流的采样率不同于图采样率时重采样，并把设备时钟自适应到图时钟；在
  *Pro Audio* 配置下，同一设备的节点被视为共用一个时钟，不做重采样 [35]。图采样率
  切换（`default.clock.allowed-rates`）默认关闭 [34]。

## 3. 输入与输出使用不同设备

PortAudio 的全双工流要求两个设备属于同一主机 API [9]；ASIO 要求是同一设备 [12]；
Core Audio 用两个回调之间的环形缓冲连接两个设备 [11]。两个设备就有两个时钟：若
相对速率误差为 ε，长度为 T 的扫频中录音会滑移 ε·T（举例：50 ppm、10 s 即
0.5 ms，48 kHz 下为 24 个样本）。

* **影响。** 小的失配通常不影响脉冲响应；大一些就会使其“倾斜”（skew），低频先于
  高频到达。倾斜的脉冲响应仍可用于计算房间参数，但在 Farina 的例子中，校正后峰值
  噪声比提高了 12.45 dB [1, §3.4]。漂移相当于把脉冲响应与一个全通滤波器卷积，该
  滤波器沿扫频的频率轨迹变化，群延迟与扫频长度成正比 [6]。由扫频速率决定位置的
  谐波响应 [4] 也会移动；平均 [7] 和 MLS [5] 同样受影响。
* **校正**需要知道漂移速率（来自回送或重复激励），再做重采样或补偿滤波
  [6][7]，或者使用基于参考测量的逆滤波器或拉长的逆扫频 [1, §3.4]。RoomScope 不估计
  漂移（`core/loopback.py`）。
* **建议。** 播放和录音使用同一个音频接口。在 macOS 上若必须使用两个设备，就建立聚合
  设备，把时钟最可靠的设备设为时钟（同步）源，并对其他设备开启漂移校正（即重采样），
  或者用字时钟锁定它们并关闭漂移校正 [27][28]（HAL 属性：
  `kAudioSubDevicePropertyDriftCompensation` [29]）。非 Pro Audio 配置下的 PipeWire
  会把设备重采样到其图时钟 [35]：漂移被隐藏，代价是重采样。
* **回送能暴露漂移。** 把输出设备回送到输入设备的第二个输入；回送会显示
  同样的倾斜。RoomScope 会拒绝峰值后 10 ms 内能量不足 99 % 的回送，其补偿窗口
  只覆盖峰值前 5 ms 到峰值后 15 ms（`core/loopback.py`），因此无法吸收更大的倾斜。
  播放和录音是不同物理设备时 RoomScope 会给出警告（`audio/inventory.py`）。

## 4. RoomScope 如何探测设备

* **列举：** `sd.query_devices()`、`sd.query_hostapis()` [14]。默认采样率是
  PortAudio 的 `defaultSampleRate`：WASAPI 上是混音格式采样率 [10]，Core Audio 上是
  标称采样率 [11]，JACK 上是服务器采样率，ALSA 上是设备默认值或不经重采样时最接近
  44.1 kHz 的采样率 [12]。
* **采样率检查：** `check_sample_rate()`（`audio/devices.py`）调用
  `sd.check_input_settings()` / `sd.check_output_settings()`，即
  `Pa_IsFormatSupported` [9][14]。界面在每次测量前检查所选设备的所选采样率，命令行
  检查 `--input-device` / `--output-device` 指定的设备，设备清单
  （`audio/inventory.py`）检查 44.1、48、88.2、96、176.4 和 192 kHz。检查时只用**一个声道**（`channels=1`）；不指定声道数时 sounddevice 会补上设备的最大声道数，设备只在较少声道下才支持的采样率就会检查失败 [11][14]。检查使用 `'high'` 延迟且不带主机专用设置（WASAPI 共享、Core Audio“友好共享”）[14]。
* **不启动任何流**，但 ALSA 会打开 PCM 并应用硬件参数，Core Audio 会打开再关闭一个
  流来回答 [11][12]。建议延迟会被忽略 [9]。
* **“支持”不等于“原生”。** MME 和 DirectSound 接受由 Windows 转换的采样率 [16]
  （PortAudio 的 DirectSound 代码根本不检查采样率 [12]）；WASAPI 共享模式只接受引擎
  采样率，但仍会处理信号 [10][21]；Core Audio 默认会转换 [11]；ALSA 的 `plughw:`、
  `default`、`pulse` 和 `pipewire` 会转换 [32][35]；ALSA 和 OSS 接受 1 % 以内的
  采样率 [12]。只有 `hw:`、WDM-KS、WASAPI 独占、ASIO 和 JACK 反映硬件或服务器实际
  运行的采样率。
* **一次测量只用一个主机 API。** 全双工流要求两个设备属于同一主机 API，否则 `Pa_OpenStream` 以 `paBadIODeviceCombination` 失败 [9]。RoomScope 在播放前检查这一点；只选了一个设备时，另一方向使用同一主机 API 的默认设备（`audio/inventory.py` 的 `resolve_duplex`）；在 Windows 上系统默认设备属于 MME，与 WASAPI 选择不匹配。超出设备声道数的声道会在播放前被拒绝（`check_channels`），之后才向流实际要打开的设备、按流实际打开的声道数询问采样率（`Pa_IsFormatSupported`）。图形界面和 `roomscope measure` 执行同一个 `preflight`。
* **测量本身：** 一个全双工 `sd.Stream`：float32、256 帧块、设备的默认高延迟，
  “typically more robust” [14]（`portaudio.py`）；`--latency low` 改用默认低延迟。

## 4a. 软件能力目录（不是硬件结果）

这些是 RoomScope 自己的参数和 PortAudio 文档中的默认值。它们补全产品自带的
设备列表、声道数、测量采样率和主机 API 表。它们**不会**填入
[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)。

| 来源 | 补全的内容 |
| --- | --- |
| `SUPPORTED_SAMPLE_RATES`（`models/configuration.py`） | 44100、48000、88200、96000、176400、192000 Hz：RoomScope 会向 `Pa_IsFormatSupported` 询问的全部采样率 |
| `FakeBackend.list_devices` | 一台合成设备：**8 入 / 2 出**，默认 48 kHz，上述全部六种采样率。不会播放任何声音。 |
| `HOST_API_PREFERENCE` / `HOST_API_NOTES`（`audio/inventory.py`） | Windows、macOS、Linux 上每个主机 API 的优先级和测量说明 |
| `HOST_API_DOCUMENTED_LATENCY` | §2 中 PortAudio 编译默认的低/高延迟（不是测得的往返延迟） |

`roomscope devices --json` 和 `roomscope doctor --json` 每次都会带上
`supported_sample_rates` 和 `host_api_catalog`。没有 PortAudio 设备的机器
仍然报告该目录和这六种采样率；在出现接口之前，`devices` 数组保持为空。

独立模式会话现在把同样的参数写入 `session.audio_interface`（名称、主机 API、
声道数、已公布的采样率）和 `session.bit_depth`（`32-bit float`，即
`roomscope measure` 写出的 FLOAT 文件）。通用 DAW 模式把这些字段留空：设备链
由 DAW 掌管。

## 4b. 引用的目录（不是 RoomScope 测量）

这些行来自公开的厂商页面和开源仓库。它们补全本机无法探测的声道数、采样率、
位深度和主机 API 编译默认值。它们**不是**实体接口测试，也**不会**填入
[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)。

`roomscope devices --referenced` 和 `roomscope devices --json` 的 `referenced`
对象打印同一张表。每个值带有来源 URL 和定位（`src/roomscope/audio/referenced.py`）。

来源与空缺的英文对照见 [AUDIO_DEVICES.md](AUDIO_DEVICES.md) §4b。

## 5. 参考文献

访问日期 2026-09-24。另见 [research/literature.md](research/literature.md)。文献条目保留原文。

1. A. Farina, "Advancements in Impulse Response Measurements by Sine Sweeps," AES 122nd Convention, Vienna, 2007 May 5–8, paper 7121 (AES E-Library 14106). Author PDF, §3.4 "Clock mismatch": https://www.angelofarina.it/Public/Papers/226-AES122.pdf
2. S. Müller, P. Massarani, "Transfer-Function Measurement with Sweeps," J. Audio Eng. Soc. 49(6), 443–471, 2001 June (AES E-Library 10189). Author copy, §1.7, §2.2, §2.4: https://audioroundtable.com/misc/Mueller.pdf
3. A. Torras-Rosell, F. Jacobsen, "A New Interpretation of Distortion Artifacts in Sweep Measurements," J. Audio Eng. Soc. 59(5), 283–289, 2011 (AES E-Library 15929). https://orbit.dtu.dk/en/publications/a-new-interpretation-of-distortion-artifacts-in-sweep-measurement/
4. A. Novák, P. Lotton, L. Simon, "Synchronized Swept-Sine: Theory, Application, and Implementation," J. Audio Eng. Soc. 63(10), 786–798, 2015. doi:10.17743/jaes.2015.0071; https://hal.science/hal-02504321v1
5. P. Svensson, J. L. Nielsen, "Errors in MLS Measurements Caused by Time Variance in Acoustic Systems," J. Audio Eng. Soc. 47(11), 907–927, 1999 November. https://aes2.org/publications/elibrary-page/?id=10266
6. N. J. Bryan, M. A. Kolar, J. S. Abel, "Impulse Response Measurements in the Presence of Clock Drift," AES 129th Convention, San Francisco, 2010 November 4–7 (AES E-Library 15592). https://ccrma.stanford.edu/groups/chavin/publications/AES129_ClockDrift.pdf
7. H. Gamper, "Clock drift estimation and compensation for asynchronous impulse response measurements," Proc. HSCMA 2017, San Francisco, pp. 186–190. doi:10.1109/HSCMA.2017.7895587; https://www.microsoft.com/en-us/research/wp-content/uploads/2017/03/Clock_drift_estimation_HSCMA_2017.pdf
8. ISO 18233:2006, *Acoustics — Application of new measurement methods in building and room acoustics*. https://www.iso.org/standard/40408.html (scope read in the public preview; its clauses on the measurement system were not checked).
9. PortAudio v19.7.0, `include/portaudio.h` and `src/common/pa_front.c`. https://github.com/PortAudio/portaudio/blob/v19.7.0/include/portaudio.h, https://github.com/PortAudio/portaudio/blob/v19.7.0/src/common/pa_front.c
10. PortAudio v19.7.0, WASAPI: `include/pa_win_wasapi.h`, `src/hostapi/wasapi/pa_win_wasapi.c`. https://github.com/PortAudio/portaudio/blob/v19.7.0/include/pa_win_wasapi.h
11. PortAudio v19.7.0, Core Audio: `include/pa_mac_core.h`, `src/hostapi/coreaudio/pa_mac_core.c`, `pa_mac_core_utilities.c`, `notes.txt`. https://github.com/PortAudio/portaudio/tree/v19.7.0/src/hostapi/coreaudio
12. PortAudio v19.7.0, host APIs `wmme`, `dsound`, `wdmks`, `asio`, `alsa`, `jack`, `oss`. https://github.com/PortAudio/portaudio/tree/v19.7.0/src/hostapi
13. PortAudio, "API Overview". https://portaudio.com/docs/v19-doxydocs/api_overview.html
14. python-sounddevice 0.5.6: platform-specific settings, checking hardware, streams, installation, NEWS. https://python-sounddevice.readthedocs.io/en/0.5.6/api/platform-specific-settings.html, https://python-sounddevice.readthedocs.io/en/0.5.6/api/checking-hardware.html, https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html, https://python-sounddevice.readthedocs.io/en/0.5.6/installation.html, https://github.com/spatialaudio/python-sounddevice/blob/0.5.6/NEWS.rst
15. spatialaudio/portaudio-binaries, build workflow (checks out PortAudio v19.7.0). https://github.com/spatialaudio/portaudio-binaries/blob/master/.github/workflows/build-libs.yml
16. Microsoft Learn, "Device Formats." https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats
17. Microsoft Learn, "Exclusive-Mode Streams." https://learn.microsoft.com/en-us/windows/win32/coreaudio/exclusive-mode-streams
18. Microsoft Learn, "User-Mode Audio Components." https://learn.microsoft.com/en-us/windows/win32/coreaudio/user-mode-audio-components
19. Microsoft Learn, "About the Windows Core Audio APIs." https://learn.microsoft.com/en-us/windows/win32/coreaudio/about-the-windows-core-audio-apis
20. Microsoft Learn, "AUDCLNT_STREAMFLAGS_XXX Constants." https://learn.microsoft.com/en-us/windows/win32/coreaudio/audclnt-streamflags-xxx-constants
21. Microsoft Learn, "Audio Processing Object Architecture." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-processing-object-architecture
22. Microsoft Learn, "Windows Audio Architecture." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/windows-audio-architecture
23. Microsoft Learn, "Low Latency Audio." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/low-latency-audio
24. Microsoft Support, "Disable Audio Enhancements." https://support.microsoft.com/en-us/topic/disable-audio-enhancements-0ec686c4-8d79-4588-b7e7-9287dd296f72
25. Microsoft Support, "Turn on app permissions for your microphone in Windows." https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows
26. Apple, Audio MIDI Setup User Guide, "Set up audio devices." https://support.apple.com/guide/audio-midi-setup/set-up-audio-devices-ams59f301fda/mac
27. Apple, Audio MIDI Setup User Guide, "Set aggregate device settings." https://support.apple.com/guide/audio-midi-setup/set-aggregate-device-settings-ams094c7edb4/mac
28. Apple Support, "Create an Aggregate Device to combine multiple audio devices." https://support.apple.com/en-us/102171
29. Apple Developer, `kAudioDevicePropertyNominalSampleRate` (CoreAudio `AudioHardwareBase.h`; `kAudioSubDevicePropertyDriftCompensation` in `AudioHardware.h`). https://developer.apple.com/documentation/coreaudio/kaudiodevicepropertynominalsamplerate
30. Apple, macOS User Guide, "Control access to the microphone on Mac." https://support.apple.com/guide/mac-help/control-access-to-your-microphone-on-mac-mchla1b1e1fe/mac
31. Apple Developer, `NSMicrophoneUsageDescription`. https://developer.apple.com/documentation/bundleresources/information-property-list/nsmicrophoneusagedescription
32. ALSA project, alsa-lib, "PCM (digital audio) plugins." https://www.alsa-project.org/alsa-doc/alsa-lib/pcm_plugins.html
33. alsa-lib, `src/conf/alsa.conf` (`defaults.pcm.dmix.rate 48000`). https://github.com/alsa-project/alsa-lib/blob/master/src/conf/alsa.conf
34. PipeWire, pipewire.conf(5). https://docs.pipewire.org/page_man_pipewire_conf_5.html
35. PipeWire, pipewire-props(7), "Resampler Parameters" and `clock.name`. https://docs.pipewire.org/page_man_pipewire-props_7.html
36. PulseAudio, pulse-daemon.conf(5). https://manpages.debian.org/bookworm/pulseaudio/pulse-daemon.conf.5.en.html
37. JACK Audio Connection Kit, API reference, "Controlling & querying JACK server operation" (`jack_get_sample_rate`). https://jackaudio.org/api/group__ServerControl.html
38. Linux kernel documentation, "Notes on Kernel OSS-Emulation." https://www.kernel.org/doc/html/latest/sound/designs/oss-emulation.html
