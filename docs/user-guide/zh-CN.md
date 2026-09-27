# RoomScope 用户指南

RoomScope 用来测量录音房间，让你听到房间对近距离拾音声源做了什么。它不给房间打分，也不做校正。

英文原文见 [en.md](en.md)。

## 安装

**用 Python。** RoomScope 尚未发布到 PyPI，请从 GitHub 安装到虚拟环境（需要 Python 3.12 或更高）：

```bash
python3 -m venv roomscope-env
source roomscope-env/bin/activate          # Windows: roomscope-env\Scripts\activate
pip install "roomscope[gui] @ git+https://github.com/jingyemingyue/RoomScope.git"
```

只用命令行可去掉 `[gui]`。使用 pipx：`pipx install git+https://github.com/jingyemingyue/RoomScope.git`。
从源码开发请用 `pip install -e ".[dev,gui]"`（见 CONTRIBUTING.md）。`pip install roomscope` 是计划中的功能，目前还不可用。

**未签名桌面包。** `release.yml` 会为 macOS、Windows、Linux 打出一目录布局的包，维护者发布 Release 后会出现在 Releases 页面（目前尚未发布）。在维护者持有签名证书之前，这些包都是**未签名**的：

* **macOS：** 右键打开，或在“隐私与安全性”里放行。系统询问麦克风权限时请允许。
* **Windows：** SmartScreen 可能拦截，选“更多信息”→“仍要运行”。
* **Linux：** 解压目录后运行 `roomscope`。

关于对话框和 `THIRD_PARTY_LICENSES/` 列出了 Qt、libsndfile 等许可证。

## 无需硬件先试用

```bash
roomscope --lang zh_CN demo
```

演示会生成扫频信号和同一个模拟房间里两个位置的**模拟录音**（一个靠近桌面和侧墙，一个向后移开），分别分析并对比。不使用任何音频设备，也不播放声音。文件保存在 `roomscope-demo/`；每个会话都标记为 `"mode": "synthetic_demo"`，不会被误认为真实测量。可以用 `roomscope show roomscope-demo/position-a`、`roomscope compare roomscope-demo/position-a roomscope-demo/position-b --same-input-gain` 或桌面程序打开。

## 通用 DAW 模式

1. `roomscope sweep --out sweep.wav`（或界面里的生成按钮）。把 `.roomscope-sweep.json` 和 WAV 放在一起。
2. 把 WAV 导入 DAW 新轨道，路由到监听。
3. 用测量话筒录第二条轨道。导出时不要裁切。
4. 可选 loopback：导出双声道（话筒 + 电回送），使用 `--channel 0 --loopback-channel 1`。
5. `roomscope analyze --recording take.wav --sweep sweep.wav --out session/`，或在界面里打开这些文件。

## 独立模式与 loopback 线

`roomscope devices` 列出设备。`roomscope measure --out session/` 播放扫描并录音。`--input-channels 1,2 --loopback-channel 2` 在输入 2 记录电回送。

先把监听开低。超过 −12 dBFS 每次都要 `--acknowledge-level`；该确认永不保存。

**演示**（界面、`roomscope demo` 或 `roomscope --backend fake measure`）在合成房间上走同一流程，不会对扬声器发声。

## 读结果

每个指标都有有效性标记。`insufficient_decay_range` 表示数字被收回，不是零。没有总分。

核心诊断（`warnings` / `notes` / `reason`）在 `result.json` 里始终是英文，方便跨语言对比缺陷。界面在标明这一点的标题下原样显示。

结果页有七个标签：

| 标签 | 内容 |
| --- | --- |
| 概览 | 宽带与倍频程 EDT / T20 / T30 / RT60 及有效性；文本报告；核心诊断（始终英文）。 |
| 脉冲响应 | 反卷积后的 IR。峰值是直达声，不会归一化到 1.0。 |
| 频率响应 | 原始（点线）与平滑（实线）幅度。虚线是电 loopback（仅在补偿成功时）。0 dB 是接口，不是“房间是平的”。 |
| 衰减 | Schroeder / 能量衰减曲线。宽带为实线；倍频程用不同虚线，不只靠颜色区分。 |
| 噪声 | 安静段频谱和 50/60 Hz 交流声候选。 |
| 早期反射 | ETC 峰值（延时 ms，相对直达声的 dB）。 |
| 摆位 | 多余路径；只有卷尺量过扬声器距离时才给出扬声器高度、设备上方平面和水平间距。不给墙面命名。 |

低频共振候选写在概览文本报告里（以及 `roomscope export` 的 `resonances.csv`），没有单独标签。

## 摆位

结果页有“摆位”标签。没有卷尺量的扬声器距离时，RoomScope 只报告每条到达的多余路径。有了距离（以及要求垂直轴时的话筒高度）后，会报告扬声器高度、两个设备上方的平面和水平间距。它从不给墙面命名，也不给出房间长宽。

在通用 DAW 模式或独立模式的分析之前填入卷尺数字，或在命令行使用 `--speaker-distance` / `--mic-height` / `--temperature`。

## 对比两个位置

`roomscope compare baseline/ candidate/ --same-input-gain`（或界面的对比页）。只有两侧都是 VALID 时，衰减差值才是 VALID。噪声差值需要明确声明“输入增益未变”。变化从不被称为显著；ISO 3382-1 对 T 的刚可察觉差只作为背景引用。

对比页列出配对的早期反射（延时 ±0.5 ms）和低频共振（1/6 倍频程内，并比较 decay-distinguishable 标志）。`roomscope compare … --out comparison.json` 只写入数字；`roomscope show comparison.json` 会再打印报告并**重新生成**解读（解读从不写入该文件）。

## 项目与平均

项目文件夹包含 `project.json` 和普通会话文件夹。
`roomscope project init --out room/ --name Booth`，再
`roomscope project add room/ session/ --position desk`。
`roomscope project average room/` 只平均有效的 T 值，从不平均衰减曲线，并标出位置数量达到的 ISO 3382-2 等级。

## 导出与语言

`roomscope export session/ --format csv --out curves/` 导出每条曲线。
`--lang zh_CN`（或设置 → 语言，或 `ROOMSCOPE_LANG`）会翻译解读、文本报告标签、界面和命令行帮助（`roomscope --help` 及每个子命令）。单位不翻译；数字保持 ASCII。`roomscope.core` 的诊断字符串保持英文。

## 排错

| 现象 | 检查 |
| --- | --- |
| 直达声置信度不高 | 扫频侧车文件不对；扬声器失真；不要裁切录音。 |
| 参考扫频不对 | WAV 旁的 `.roomscope-sweep.json` 必须是 RoomScope 为**这次**扫描写出的文件（同一时长、频带和淡入淡出）。用另一次会话的侧车，或把录音本身当参考，都会找错 IR。 |
| 一次导出里有多遍扫描 | 只播放一遍。同一 WAV 里两遍扫描会像两条 IR；RoomScope 保留最强峰，其余被当成“房间”。一次只导出一条 take。 |
| 削波警告 | 降低回放或输入增益。 |
| 衰减范围不足 | 加长扫描、略提高回放，或换更安静的房间。 |
| 设备采样率不符 | 界面会在请求采样率旁边显示设备实际采样率。 |
| loopback 被拒绝 | 回送必须像电脉冲，不能是房间响应。若第二声道是另一支话筒，补偿会被拒绝，分析在未补偿路径上继续。 |

## 缺陷报告打包

`roomscope session bundle session/ --out report.zip` 打包会话。
`--no-audio` 可去掉 WAV，避免分享房间录音。把 zip 附在测量类 issue 上。设置和滚动日志在 `$ROOMSCOPE_HOME`（默认 `~/.roomscope`）。
