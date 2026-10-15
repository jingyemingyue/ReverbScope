# 社区测试：一台电脑、一个接口、一份报告

[English](COMMUNITY_TESTING.md) | **简体中文**

先按[公开 beta 安装指南](PUBLIC_TESTING.zh-CN.md)安装，或使用维护者明确分享的候选构建，记录文件 SHA256
和构建提交。[硬件矩阵](HARDWARE_TESTS.zh-CN.md)在真实执行并报告前保持 **NOT RUN**。
2026-10-15 的云端审计环境没有你的 Mac、声卡、测量话筒、扬声器或 DAW，不能提供实测通过结论。

## 状态的含义

| 状态 | 含义 | 必要证据 |
| --- | --- | --- |
| Automated PASS | 指定提交、环境中的自动化检查通过 | 命令、退出码、日志或 CI；合成输入标注 Synthetic / Demo |
| Hardware PASS | 人在真实设备上执行该项并通过 | 日期、版本/SHA、电脑、接口/驱动、路由、采样率/缓冲、附件、Issue |
| FAIL | 已执行，但结果不满足预期 | 实际现象、报错、复现步骤；说明自动化或实机场景 |
| NOT RUN | 未执行、设备不支持或缺少证据 | 写明原因；不能从别的采样率、系统或 DAW 推断通过 |

环境报告和采样率探测不能证明完整录音成功；厂商手册不能证明兼容性。
驱动报告延迟不等于独立测量的往返延迟。旧矩阵的 PASS 只能表示真实 Hardware PASS，并需关联原始报告。

## 每轮生成一份报告

在源码目录中，使用 Python 3.12+（工具只用标准库）：

```bash
python scripts/prepare_test_report.py --out test-reports/mac-48k --probe --daw "Fender Studio Pro: fill version" --language zh-CN
```

程序没有加入 PATH 时，使用 `--executable` 指定**正在测试的应用**。Mac 更名候选版示例：

```bash
python scripts/prepare_test_report.py --out test-reports/mac-candidate --executable /Applications/ReverbScope.app/Contents/MacOS/ReverbScope --probe --language zh-CN
```

公开 beta 1 使用 `/Applications/RoomScope.app/Contents/MacOS/RoomScope` 或 `--executable roomscope`。
不要测试安装包却采集源码环境。`--skip-environment` 只生成空表，`--language en` 生成英文表。
`--probe` 短暂询问设备支持的采样率，不播放/录音；不会上传任何内容。

输出到**新目录**：`report.md`、`run.json`、`environment.json`、`commands.txt`。
已存在目录会被拒绝，以免覆盖已有实测。即便环境采集成功，所有硬件/DAW 行仍从 NOT RUN 开始。
采集 JSON 省略路径、设置和原始异常文字；设备名仍可能含私人姓名，发布前逐项检查。
采集失败会记录 FAIL，不会复制可能含私人路径的异常全文。

不装 Python 也可复制下表，并在被测应用中复制“帮助 → 用于问题报告的环境报告”，或运行其 `doctor --probe`。
旧公开版名为 RoomScope。手工补齐同样的字段即可。

## Apple Silicon Mac 最短验收

使用真正的 arm64 桌面安装包，原生启动并允许麦克风权限。离屏截图、Rosetta 或只启动源码不能替代。
连接实体声卡、话筒与音箱；记录系统、驱动、输入输出编号、缓冲，以及是否启用 Core Audio 改采样率选项。
从 **−20 dBFS** 开始，调低监听音量，关闭话筒到音箱的直接/软件监听、效果与回送反馈。
若要对频率响应作可靠结论，应使用测量话筒；普通话筒须写明限制。

| 步骤 | 操作与通过标准 | 初始状态 |
| --- | --- | --- |
| 1 | 核对包哈希，安装、原生启动、切换中英与调整窗口；关键控件和停止入口始终可达 | NOT RUN |
| 2 | 设备枚举正确，通道数正确；实际选择输入输出并验证映射，如有则再测第 2 通道以外 | NOT RUN |
| 3 | 分别以 44.1、48、96 kHz 完整播放、录音和分析，记录请求/报告采样率且无丢帧警告；不支持的速率记 NOT RUN 并解释 | NOT RUN |
| 4 | 新一轮扫频中点停止：声音立即停、界面恢复，取消的测量不能冒充成功结果；听感不能证明一个回调内停止的精确时限 | NOT RUN |
| 5 | 调低监听后在测量中拔声卡：出现错误/取消，不挂死、不崩溃、不生成假成功；重插、刷新并再完成一次 | NOT RUN |
| 6 | 完整测量后复制日志中的 `audio stream:`、缓冲警告、`latency_s`、block size、请求/报告 Hz；不冒充实测延迟 | NOT RUN |
| 7 | 具备合适的线路电平线材和独立输入时做物理回送，无反馈，完成测量并核对补偿状态/原因；缺线或输入记 NOT RUN | NOT RUN |
| 8 | 保存成功测量，记录数值与有效性，退出、重启、打开该会话；数值、状态、图表及预期录音/sidecar 一致 | NOT RUN |

首次反馈先做 1–3、停止与保存重开即可；其余完成前不能声称整套 Mac 验收通过。
缺设备的物理行保持 NOT RUN。未经校准/参考比对，不宣称绝对 SPL 或准确度。

## Fender Studio Pro / Studio One：第一份 DAW 实测

使用**通用 DAW 模式**。当前源码/候选版按钮为“保存测试信号 WAV…”“选择录音…”“选择参考扫频…”和“分析”；其他 Draft GUI 可能不同，
记录真实版本与按钮，不要混用 PR 截图。[厂商文档来源指南](user-guide/daw-setup.zh-CN.md)用于核对菜单；
以下步骤在本审计中仍为 **NOT RUN**。

1. 新建空 Session/Song，工程 **48 kHz**，使用同一实体接口，关闭导入音频跟随工程速度。
   生成 48 kHz 扫频，保留 JSON sidecar，导入播放轨，仅路由到指定音箱。
2. Track Inspector 的 **Tempo → Don't Follow**；Event 的 Speedup 为 1，Transpose/Tune 为 0，
   Normalize 关闭。移除轨道和总线效果、自动 EQ 与房间校正。
3. 另建单声道话筒轨，准备录音后关闭 Monitor 和声卡直接监听，避免反馈。
   完整录下前置安静段、扫频和衰减尾音，不循环、不裁断扫频。
4. 只导出**话筒录音**：Export Selection 或只选话筒轨的 Export Stems。
   WAV、工程采样率，优先 32-bit float；不归一化、变速、改增益或加效果。保留原录音和 sidecar。
5. 用扫频定义导入录音并分析。记录直达声置信度与全部健康/有效性警告。
   完整物理往返的通过标准是分析完成、直达声置信度 high，且没有非预期采样率/伸缩诊断。
   警告应继续调查，不能换成演示结果。保存、退出、重新打开本次会话。
6. 可选负例：在 44.1 kHz 工程故意不转换地播放 48 kHz 扫频；另一轮将片段变为 97% 长度。
   记录 DAW 是否自动重采样及实际诊断；正确重采样未必产生不匹配诊断。完成后恢复干净设置。

## 其他 DAW 的复用模板

| DAW | 必填设置与参考 | 初始状态 |
| --- | --- | --- |
| Pro Tools | [指南](user-guide/daw-setup.zh-CN.md)：准确版本、工程速率、SRC 选项、话筒监听关闭、所选录音导出 | NOT RUN |
| Logic Pro / GarageBand | [指南](user-guide/daw-setup.zh-CN.md)：版本、Flex/Smart Tempo、关闭归一化、话筒导出与尾音 | NOT RUN |
| REAPER | [指南](user-guide/daw-setup.zh-CN.md)：版本、工程/设备采样率、timebase、rate 1.0、仅话筒渲染 | NOT RUN |
| 其他 DAW | 同一扫频 → 实体录音 → 无处理话筒导出 → sidecar 分析，并记录导入/伸缩/导出设置 | NOT RUN |

每个 DAW/版本/路由组合单独一份报告。`--daw` 只记录标签，不启动或控制 DAW，也不判定兼容。

## 提交、复现、修复与回归

附件：填写后的表、检查过的 `environment.json`、包哈希、相关 `audio stream:` 与警告、结果截图、
DAW 导出与伸缩设置截图。优先用 `session bundle <session> --no-audio --out report.zip`；
即使不含音频，也检查房间标签、路径和 JSON 元数据。录音须经同意且无私人语音；不要上传整个私人 DAW 工程。
生成的 `commands.txt` 列出被测应用所需命令。

提交[声卡中文表单](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware-zh-CN.yml)
或[DAW 中文表单](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw-zh-CN.yml)。
维护者确认版本与范围，复现失败，加入最小且无隐私的回归样本，在正确分支修复，邀请报告者用新构建复测。
审核后才将带日期、Issue 链接的实测行写入矩阵。保留过去 FAIL/NOT RUN，修复不等于 Hardware PASS。
