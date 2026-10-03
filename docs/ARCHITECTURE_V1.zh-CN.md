# ReverbScope v1.0 架构设计（中文摘要）

[English](ARCHITECTURE_V1.md) | **简体中文**

> 状态：**提案，2026-09-22**，供维护者评审。本文是
> [ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) 的摘要而非逐字翻译；两者不一致时以英文版为准。
> [ARCHITECTURE.md](ARCHITECTURE.md) 描述 v0.1 已有的东西，本文描述"开放给所有人"的
> v1.0 要新增什么、冻结什么、继续拒绝什么。除标注"已落地"或"PR #2 中"的条目外，
> 以下内容均尚未实现。只能由项目发起人决定的事项标注为 **维护者决定**，汇总在第 11 节。

## 1. 一句话定位

v0.1 用合成房间证明了测量链路，并给开发者一个可以 clone、测试、评审的仓库。
"开放给所有人"意味着同一条链路要交到三种人手里：

| 受众 | v1.0 提供 | 他们永远不需要 |
| --- | --- | --- |
| 录音师、学生、家庭录音用户 | 签名的桌面应用；DAW 四步流程与 Standalone 模式；中英文用户指南；两个位置的对比；可以直接发给别人求助的会话文件夹 | Python、终端、账号、联网、校准麦克风 |
| 集成者与研究者 | `pip install reverbscope`；带稳定性承诺的公开 API；`result.json` / `session.json` / `comparison.json` 及其 JSON Schema；曲线 CSV 导出；`reverbscope analyze-ir` 分析其他工具产出的脉冲响应 | 逆向 JSON 结构；导入私有模块 |
| 贡献者、翻译者 | 不碰 DSP 就能加 Recording Profile、导出器和翻译；跨平台 CI；记录"为什么"的 ADR；作为回归证据的真实房间验证数据 | DSP 背景；改 Python 才能翻译 |

## 2. 原则

v0.1 与需求书中的原则全部保留：DAW-independent、Core-first、科学正确性优先、诚实的数字
（未校准只报 dBFS、没有房间评分）、许可证清晰、安全（保守电平、不碰系统音频设置）。

v1.0 新增四条：

* **兼容性是功能。** 任何 1.x 写出的文件，所有更高的 1.x 都能读。读取宽松（未知键忽略并记日志），写入严格（测试中按 Schema 校验）。
* **会话自包含。** 一个会话文件夹带着重新分析和报告 bug 所需的一切：扫频定义、原始录音（按需复制）、脉冲响应、结果与元数据。解释性 Findings 是派生数据，打开时重新生成，从不当作真相存储。
* **从构造上离线。** 包内没有任何网络代码，CI 检查 `src/` 下不得 import `socket` / `urllib` / `http` / `requests` / `ssl`。更新检查、崩溃上报、遥测在 1.x 里不是"默认关闭"，而是不在范围内。
* **不 fork 也能扩展。** Profile、导出器、语言包通过 entry point 与 gettext 目录发现。
* **"停止"是安全控制。** 任何驱动音箱的操作都能立即中止，中止时先静音输出再做别的。

## 3. 范围

### 3.1 MUST（发布阻断项）

| # | 条目 |
| --- | --- |
| M1 | 公开 API 分层与 `reverbscope` 顶层导出（§5.1） |
| M2 | result / session / comparison / sidecar 的 JSON Schema；宽松读取；`AnalysisResult.from_dict`（PR #2 中） |
| M3 | 重新打开会话与会话浏览器（PR #2 中） |
| M4 | 两次会话的对比（core、CLI、GUI、解释层）——回答需求书的第三个问题"换位置以后有没有改善" |
| M5 | Loopback 参考通道（DAW 双轨导出；Standalone 双通道采集）——去除声卡自身响应，并给出电气时间零点 |
| M6 | 音频后端接口、假后端（测试与演示模式）、进度、立即停止 |
| M7 | 国际化框架；Findings、GUI、CLI 的简体中文目录 |
| M8 | 自包含会话、bug 报告打包、用户设置 |
| M9 | PyPI 发布（trusted publishing）；macOS / Windows / Linux 桌面包，附许可证包与 GPL 模块门禁 |
| M10 | 跨平台 CI、不可信文件的健壮性测试、每个平台至少跑一次硬件测试矩阵 |
| M11 | 真实房间验证活动，连同数据一起发布 |
| M12 | 中英文用户指南（测量、读图、对比、排错） |
| M13 | 仓库公开检查清单执行完毕（**维护者决定**） |

### 3.2 SHOULD（计划内，延期不阻断 1.0）

`analyze-ir` 脉冲响应导入；同一房间多次会话的 T 值空间平均（按 ISO 3382-2 标注精度等级）；
项目文件夹（一个房间、多个位置）；CSV 导出器与导出器 entry point；GUI 的 Placement 标签页；
CI 加入 Python 3.14；由 `docs/` 生成的文档站（`scripts/build_docs_site.py`）。

### 3.3 v1.0 不做（设计上拒绝，或带理由推迟）

* **插件（VST3 / AU / AAX）。** WAV 已经保证 DAW 无关；VST3 SDK 是 GPLv3 / 商业双许可，AAX 需要 Avid 协议，开放仓库无法满足。将来的插件外壳必须跨进程边界调用 Apache-2.0 的核心，该边界本身是 1.0 之后的事，且要先做许可证审查。
* **独立播放/录音设备之间的时钟漂移估计或校正。** 超出"单一全双工声卡"的假设，且是有效专利 US 10,816,391 B2 的主题。Loopback 通道只用一台设备、一个时钟，不估计漂移。
* **自动双扫频通带方案**（US 9,959,883 B2）。仍然一次扫频。
* **dB SPL。** 模型里预留校准槽位（§5.3.5），1.0 不提供校准流程，所有电平仍是 dBFS。
* **多位置的摆位几何。** 需要冗余的第三个位置与简并性规范化，尚未设计。
* 房间评分、自动 EQ / 校正、房间模态识别、3D 建模、吸音材料计算、云、账号、遥测、更新检查——与需求书一致。

## 4. 包布局变化要点

`reverbscope.core` 仍只有一个入口 `pipeline.analyze`，新增三个纯函数：
`loopback.compensate`、`compare.compare`、`averaging.average_decay`，规则不变：
NumPy 进、dataclass 出，无 I/O、无 Qt。其他新增：

* `reverbscope/__init__.py` 惰性导出 Tier 1 API；`__main__.py` 供桌面包使用；`settings.py`；`i18n.py`；`locale/`；`schemas/`。
* `models/`：`comparison.py`、`project.py`、`calibration.py`；`result.py` 加 `LoopbackResult` 与 `reverbscope_version`。
* `io/`：`project_store.py`、`exporters/`；`session_store` 支持复制录音、打包。
* `audio/`：`backend.py`（协议）、`portaudio.py`（现有代码改为回调流，支持进度与取消）、`fake.py`。
* `interpretation/registry.py`：内置 Profile + entry point 组 `reverbscope.profiles`。
* `cli/`：新增 `analyze-ir`、`compare`、`session`、`export`、`schema`；全局 `--format`、`--lang`、`--backend`。
* `ui/`：`compare_view.py`、`settings_dialog.py`；PR #2 的 `browser.py`。

依赖方向不变：`core` 永不 import `io` / `audio` / `ui` / `cli` / `settings` / `i18n`；`core` 产生的所有字符串保持英文并原样存入 `result.json`。

## 5. 关键设计

### 5.1 公开 API 分层

* **Tier 1（公开，SemVer 承诺）：** `reverbscope` 顶层导出的名字、JSON 文件及其 Schema、`--format json` 输出、CLI 退出码。删除或改义需要主版本号；弃用提前一个次版本用 `DeprecationWarning` 通告。
* **Tier 2（有文档）：** MEASUREMENT_METHODOLOGY.md 点名的 `core` 函数、`AudioBackend`、`RecordingProfile`、entry point 组。可以加带默认值的关键字参数，变更写进 CHANGELOG。
* **Tier 3（内部）：** `ui`、`cli` 内部、下划线开头的一切。

文本报告不是接口：措辞会本地化、会变。

### 5.2 Schema 与文件格式

`schema_version` 只在 1.0 的读取者可能误解时才递增（键改名、单位改变、时间原点改变）；加可选键不递增。`MeasurementSession.from_dict` 现在拒绝未知字段，v1.0 改为忽略并记日志，只拒绝更高的 `schema_version`。Schema 文件手写、随包分发，测试证明每个 dataclass 能通过其 Schema 往返；`jsonschema`（MIT）只作为测试依赖。Findings 不存储，打开会话时用记录的 profile 与当前版本重新生成，报告注明两者。

### 5.3 Loopback 参考通道（M5）

声卡的一路输出既驱动音箱，也用线缆（或声卡内部 loopback）回送到第二路输入。使用前先验证 loopback 解卷积结果确实是一个电气脉冲（单次通过、pre-peak margin 高、无削波、峰后能量几毫秒内落到本底），否则拒绝补偿并说明原因，分析按无补偿继续。补偿是激励频带内的正则化除法（复用现有 `design_spectral_inverse` 的机制），带外不放大。Loopback 峰值给出电气时间零点：`path_delay_ms` 与 `distance_upper_bound_m = c · path_delay` 作为**上界**报告——音箱内部 DSP 延迟只会增加延迟，所以真实距离不超过该值。卷尺距离大于该上界时，摆位结果标为不可靠。不做时钟漂移估计（同一转换器时钟）；也不去除音箱自身响应，并明说。

### 5.4 会话对比（M4）

`compare(baseline, candidate)` 纯函数，只在**双方都 VALID** 时给出差值，否则 `NOT_COMPARABLE` 并附两边的原因。频响在公共激励频带内插值到同一对数网格后相减；早期反射按 ±0.5 ms 配对；低频共振按 1/6 倍频程配对；噪声差值只有在双方都有已验证的安静段且用户明确声明"输入增益未变"时才有效；报告引用 ISO 3382-1 给出的 T 的可觉察差（约 5 %，条款待核对），但从不自行宣称"显著"。解释层新增 `interpret_comparison`，复用各 Profile 自己的阈值。结果存为 `comparison.json`（不写入 findings）；`reverbscope show comparison.json` 重新生成解读。GUI 对比页列出配对反射与共振。

### 5.5 音频后端（M6）

`AudioBackend` 协议：`list_devices`、`check_sample_rate`、`play_and_record(... input_channels, progress, cancel)`。PortAudio 后端从阻塞的 `sd.playrec` 改为回调流，`cancel` 在下一个回调把输出置零并关闭流。假后端合成房间（`tests/conftest.py` 的 `make_rir` 系列搬进 `audio/fake.py`），支撑 CI 里的 Standalone 测试与 GUI 的 **Demo** 模式。Windows 不用 ASIO；WASAPI 共享模式会重采样，所以测量前必须 `check_sample_rate`，GUI 并排显示设备当前采样率。

### 5.6 解释层与国际化（M7）

Profile 注册表合并内置与 entry point；第三方名字与内置冲突时忽略并警告。`Finding` 增加 `message_id`、`params`、`locale`，句子通过 gettext `_()` 用命名占位符渲染，阈值变化不会让翻译失效。机制是标准库 gettext，`.po` 提交、`.mo` 打包时编译，Babel（BSD-3）仅作开发依赖。**刻意不翻译**的部分：`core` 产生的诊断字符串（warnings / notes / reason），它们存在 `result.json` 里、出现在 bug 报告里、跨版本比较，必须与界面语言无关；GUI 在一个翻译过的标题下原样显示，并记录为已知限制。数字在所有语言里保持 ASCII 数字与小数点，单位不翻译。

### 5.7 CLI 契约

退出码：0 成功；1 `ReverbScopeError`；2 用法错误或安全拒绝（电平确认）；130 中断。`--format json` 在 stdout 只输出 `result.json` 载荷加 `findings`，诊断全部走 stderr；`--json` 保留一个次版本作为别名后移除。

文本输出由 `reverbscope/cli/console.py`（样式、状态符号、按显示宽度换行与制表）和 `reverbscope/cli/render.py` 排版，其他模块不写转义序列。颜色依次由 `--color`、`NO_COLOR`、`FORCE_COLOR`、`TERM=dumb` 决定，`auto` 只在终端上着色：管道和文件永远收不到转义序列或回车符。每个状态都同时带符号和文字（`✓` / `!` / `×` / `→`；流无法编码这些符号时用 `[OK]` / `[WARN]` / `[ERROR]` / `->`），颜色从不单独表达信息；在这样的流上，`Δ`、`→`、`–` 等符号也改用 ASCII，编码较窄的终端会替换无法显示的字符而不会报错。宽度计算中一个中日韩字符占两列；排版最宽 100 列。

每个命令的输出结构相同：标题与上下文、结果（分析和对比先给“概览”）、细节，最后是编号的下一步。普通用户错误只显示一个错误块（`× 错误：…`、说明和可以尝试的命令），退出码按文档约定；只有加 `--verbose` 才显示回溯。直接运行 `reverbscope` 会在 stderr 上显示简短的首页，退出码仍是用法错误的 2。`measure` 把设备方案和检查结果写到 stdout，进度写到 stderr（终端上是一行原地刷新，否则只有一行阶段提示；由等待线程绘制，从不在音频回调里）。文本版式不属于 Tier 1 接口。图形界面的“完整报告”面板以纯文本显示同样的 `render.py` 报告；开发者工具里的环境报告仍使用 `diagnostics.format_environment_report`。

### 5.8 存储

会话文件夹在现有三个文件之外，总是复制 `sweep.reverbscope-sweep.json`，按需（GUI 默认开）复制 `recording.wav`。项目文件夹 `project.json` 只是索引，会话仍可独立打开。`reverbscope session bundle` 打包会话供 bug 报告，`--no-audio` 可排除录音。`REVERBSCOPE_HOME`（默认 `~/.reverbscope`，PR #2 引入）存放最近会话、设置与日志。电平确认永不持久化。

## 6. 分发（M9）

* **PyPI：** `reverbscope` 名称 2026-09-22 核实可用，应在第一个预发布前注册（**维护者决定**）。纯 Python wheel + sdist，trusted publishing（OIDC，无长期 token），发布环境需维护者批准。`pipx install "reverbscope[gui]"` 是有 Python 的用户的推荐路径；`gui-scripts` 提供 Windows 无控制台启动器。
* **桌面包：** PyInstaller one-dir（macOS `.app` 装入 `.dmg`；Windows zip + Inno Setup；Linux AppImage 在最旧受支持 Ubuntu LTS 上构建），保持 Qt、libsndfile、libquadmath 为可替换的共享库以满足 LGPL。macOS 分 arm64 / x86_64 两个包。
* **打包门禁（CI 阻断）：** 包内不得含 GPL-only Qt 模块（白名单 QtCore / QtGui / QtWidgets / Linux 上的 QtDBus）、不得含 `*asio*.dll`、必须含 `scripts/build_license_bundle.py` 生成的 `THIRD_PARTY_LICENSES/`（含 LGPL/GPL 文本、Qt 与 PySide6 源码指针、FreeType 致谢、PortAudio 许可证等）。DEPENDENCIES.md §6 中 UNKNOWN / NEEDS REVIEW 的条目必须在第一个包发布前解决。
* **签名：** macOS 需 `NSMicrophoneUsageDescription`、hardened runtime、audio-input entitlement、Developer ID 签名与公证；Windows 需 Authenticode。身份只能由维护者持有（**维护者决定**）；未签名的包明确标注并在用户指南里给出绕过步骤。
* **发布流程：** 维护者推 `v*` tag 触发 `release.yml`：全矩阵测试 → PyPI（rc 作为预发布）→ 三平台打包与门禁 → `SHA256SUMS`、CycloneDX SBOM、许可证包 → 草稿 Release，由维护者发布。版本号唯一来源是 `pyproject.toml`，测试确保 `__version__` 一致。

## 7. 质量门槛（M10、M11）

* CI：lint 加无网络 import 门禁与 Tier 1 导出测试；测试矩阵 Ubuntu / macOS / Windows × 3.12，Ubuntu 另跑 3.13 / 3.14；Schema 校验作业；wheel 干净安装；打包作业。
* 测试层级：合成单元与集成（新增 loopback 补偿、对比、平均）；离屏 GUI；**健壮性**（畸形 WAV / JSON / sidecar / 会话文件只能抛 `ReverbScopeError`）；**真实 fixture**（几秒钟的真实录音，CC0，只作回归证据，不作唯一证据）；手动硬件矩阵（`docs/HARDWARE_TESTS.md`）。
* **验证活动：** 至少两个房间（处理过 / 未处理）× 两个位置，同一个录音 WAV 分别用 ReverbScope 与参考仪器（REW 只作比较仪器，或许可证清晰的开源工具箱）分析，按频带比较 T20 / T30、EDT、最强早期反射延迟、loopback 补偿后的频响；容差在测量前写下；不达标则阻断 1.0，但结果照样发布。摆位几何用卷尺核对 `source_height_m` 与 `ceiling_height_m`。

## 8. 安全与隐私

攻击面只有用户打开的文件与音频设备；JSON 读取限制大小与深度，不用 `pickle`、`eval`、shell。供应链：Dependabot、Actions 按 SHA 固定、打包锁文件、每次发布附 SBOM 与校验和。隐私：一切留在本机；会话可能包含私人空间的录音，打包支持 `--no-audio`，issue 模板先说明打包内容。SECURITY.md 在 1.0 时更新受支持版本。

## 9. 社区与治理

* **仓库公开检查清单（M13，维护者决定）：** 描述与 topics、`main` 分支保护（CI 必过、禁 force-push）、`CODEOWNERS`（core、方法学文档、许可证文档）、私密漏洞报告、标签、Discussions、置顶路线图。建议时机：第一个 rc，让候选版本先经受外部测试。
* **贡献阶梯：** Profile 与翻译是入口（一个类 + 注册 + 合成测试；一个 `.po` 文件）；DSP 改动保持"公开来源 + 合成测试 + 方法学条目"。
* **ADR：** 改变 Tier 1/2 接口、Schema、依赖或方法的决定记入 `docs/adr/`；本文的决定被接受后成为 ADR-0001 起。
* DCO 签署与否是 **维护者决定**。

## 10. 里程碑（无日期，退出标准即时间表）

| 版本 | 主题 | 内容 | 退出标准 |
| --- | --- | --- | --- |
| 0.2 | 重新打开与对比 | PR #2；`compare` 全链路；宽松读取；Schema 与 Schema CI；Tier 1 导出 | 任何 v0.1 会话能重新打开；两次会话可对比且每个差值带有效性；`reverbscope schema` 与随包文件一致 |
| 0.3 | 信任链路 | Loopback；`AudioBackend` + 假后端 + 进度 + 停止；`analyze-ir`；跨平台 CI；健壮性测试；硬件矩阵开始 | 合成声卡响应在既定容差内被去除；真机上"停止"在一个回调周期内静音；Standalone 流程在三平台 CI 上运行 |
| 0.4 | 给所有人 | i18n + zh-CN；自包含会话、打包、设置；演示模式；项目与平均（SHOULD）；CSV 导出；用户指南；三平台未签名包与许可证包、GPL 门禁 | 没有 Python 的人装上包，用中文或英文完成演示与一次 DAW 测量；许可证包没有未解决的条目 |
| 1.0-rc | 冻结与证明 | API 与 Schema 冻结；验证活动发布；硬件矩阵完成；签名包或明确的维护者决定；仓库公开；PyPI 预发布 | 无未完成 MUST；§6–§7 所有门禁在 tag 上全绿 |
| 1.0 | 发布 | 仅 rc 后的修复 | 同上；发布说明写明验证结果与已知限制 |
| 1.0 之后 | | dB SPL 校准流程；带冗余第三位置的多位置摆位；插件外壳的进程边界（先做许可证审查）；更多语言；1/3 倍频程衰减；相位显示；文档站 | |

## 11. 需要维护者决定的事项

1. 仓库公开的时机：1.0-rc（建议）还是 1.0？
2. 签名身份与预算：Apple Developer Program、Windows 代码签名证书；或 1.0 明确以未签名形式发布？
3. PyPI 名称 `reverbscope` 的注册、账号归属、trusted publishing 设置。
4. 验证活动：参考仪器、房间、执行人；是否允许把 REW 当作比较仪器（其 EULA 允许使用，不允许再分发或逆向）。
5. 是否要求 DCO 签署。
6. 语言顺序：简体中文之后是繁体中文、日语、德语，还是看译者来源？
7. 是否默认把原始录音复制进每个会话（自包含但更大）。

## 12. 对现有代码的影响（改动面）

`MeasurementSession.from_dict` 改为宽松；`AnalysisResult` 加 `reverbscope_version` 与 `loopback`；
`AnalysisSettings` 加 `loopback_channel`、`calibration`；`Finding` 加 `message_id` / `params` / `locale`；
`RecordingProfile` 加 `interpret_comparison`，`_PROFILES` 移入 `registry.py`；
`audio/devices.py` + `playrec.py` 合并为 `audio/portaudio.py` 并实现 `AudioBackend`；
CLI 新增参数与子命令，`--json` 弃用；`reverbscope/__init__.py` 惰性导出；
`save_measurement` 总是复制 sidecar、按需复制录音；`tests/conftest.py` 的合成房间助手搬到 `audio/fake.py`；
CI 加 OS 矩阵、Schema 作业、无网络门禁、打包作业与 `release.yml`；
文档新增方法学 §11（对比）、§2a（loopback）、§3a（平均），DEPENDENCIES.md 加 `jsonschema`、Babel、`cyclonedx-bom`、PyInstaller、Inno Setup 行，以及 `docs/adr/`、`docs/user-guide/`、`docs/VALIDATION.md`、`docs/HARDWARE_TESTS.md`。
