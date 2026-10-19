# 交接：PR #71 设计评审 v2 → GUI 实施顺序

> 给在 `gui/photoshop-focused`（PR #71）上继续实施的 GUI 开发者。本分支只加文档，不改 `src/`；
> 下面每一项都标了**状态**：
> - **【需代码】**：`e39185c` 上不存在，需要新写 GUI 代码；
> - **【改现有】**：功能存在，需要修改；
> - **【需 core / 单独 PR】**：涉及 `core/`、`io/`、`models/` 或新回调，按 AGENTS.md 必须另开任务，不能在 GUI PR 里写；
> - **【维护者决定】**：需要维护者先裁决。
>
> 设计稿（`images/after/`）**不代表任何功能已实现**。按 AGENTS.md 八步流程执行：每一批先复述任务、列文件、等确认。
> 引用：规格 [SPEC.md](SPEC.md)，问题编号 [REVIEW.md](REVIEW.md)。

## 批次 0：先定下来的事（维护者）

| 事项 | 选项 | 建议 |
| --- | --- | --- |
| SAFE-01 / BUSY-01 / FLOW-01 / ESC-01 原始定义 | 贴出外部评审原文 | 贴到 PR #71 评论，以便按原文复核（本评审为推断） |
| SPEC §12 Δ-1…Δ-5 | 接受 / 改准则 / 按准则改设计 | Δ-2（中性灰）、Δ-4（列表 24 px）接受；Δ-3 视用户反馈；Δ-5 需书面决定 |
| 字体是否随包分发 | 见 PR #79 D-F1 | 不阻塞本批；先用 token + 系统回退 |

## 批次 1（P0）：安全与流程 —— 合并 PR #71 前必须完成

### 1.1 ESC-01 统一 Esc 调度 【需代码】

- 文件：`ui/main_window.py`（安装过滤器）、`ui/measure_strip.py:80-82, 155-157`（删除局部 `QShortcut`，改调用调度器）、
  `ui/components/details_drawer.py`（暴露 `is_overlay()` / `close`）。
- 做法：`QApplication.instance().installEventFilter(...)`，在 `KeyPress` 且 `key == Esc` 时按 SPEC §9.2 顺序处理；
  第 1 条（发声）必须在弹层之前命中——应用级过滤器能看到发往 popup 的事件。
- 分析阶段：`MeasureStrip` 显示一次“分析不可取消”（2 s），不调用任何停止。
- 测试（`tests/ui/`）：发声中焦点在打开的 `QComboBox` 弹层上 → 一次 Esc → `stop_measurement` 被调用；
  非发声、覆盖抽屉打开 → Esc 关闭抽屉；分析中 → 不停止且出现提示。
- 不能改：`StandalonePage.stop_measurement` 与 worker 停止语义（AGENTS.md：工作线程生命周期是不变量）。

### 1.2 BUSY-01 测量中锁定全局入口 【改现有】

- 文件：`ui/main_window.py:882-887`（`show_settings` 在 `standalone.is_busy() or daw.is_busy()` 时直接返回，且菜单项禁用）、
  `:571-626`（打开会话 / 项目）、`:682-700`（`show_mode` 对 `universal_daw` 也加忙碌保护）、
  `ui/analysis_workspace.py:167-174`（设置按钮随忙碌禁用）。
- 单一状态源：用已有的 `busy_changed` 信号（`ui/pages.py:474, 821`）驱动一个 `set_global_busy(bool)`，
  统一设置 `QAction.setEnabled` 和悬停原因“测量进行中”。
- 测试：发声时逐个断言 `settings_action`、`open_action`、`open_project_action`、`new_action`、两个模式快捷键为禁用；
  结束后恢复。

### 1.3 SAFE-01 电平安全前置 【改现有 + 需代码】

- 文件：`ui/pages.py:926-937`（电平控件与确认框）、`:1405-1415`（删除弹框分支，改为前置禁用）、
  `:872-874`（整条横幅 → 一行警示，SPEC §7）、`:1006-1017`（确认页加“监听音量已确认”行）。
- 新控件【需代码】：带安全区刻度的电平滑块（−40…0 dBFS，`SAFE_MAX_LEVEL_DBFS` 处刻线，超出段用 `warn` 半透明），
  与 `QDoubleSpinBox` 双向同步；放 `ui/components/level_slider.py`（新文件）。颜色只读 token。
- 规则：`level > SAFE_MAX_LEVEL_DBFS and not acknowledge` → “继续”与“开始测量”禁用，操作栏原因文字
  “先勾选‘我已把监听音量调低’”；每次 `_on_success / _on_failure / _on_stopped` 后 `acknowledge.setChecked(False)`；
  电平从安全区内跨到安全区外时也清除。
- 不能改：`SAFE_MAX_LEVEL_DBFS`、`DEFAULT_STANDALONE_LEVEL_DBFS` 数值与 `audio/backend.py`（AGENTS.md 停止条件）。
- 测试：REVIEW SAFE-01 验收 ①–④。现有“电平确认”测试改为断言按钮禁用而非弹框——**这是测试意图变化，需在 PR 中说明**，
  不得删除断言。

### 1.4 FLOW-01 步骤条 + 常驻操作栏 【改现有 + 需代码】

- 文件：`ui/pages.py:247-343`（`MeasurementSteps`、`_StepStack`、`_install_steps`）、`ui/widgets.py:193-210`（`scroll_page`）。
- 布局【需代码】：`MeasurementSteps` 拆为 左侧 `StepList`（新组件，232 / 184 px，状态 done/current/todo/locked/running/error）
  + 中间滚动表单（最大 640）+ 右侧就绪检查（≥ 1280）+ 底部 `ActionBar`（48 px，**放在滚动区外**）。
- 每步提供 `is_complete() -> tuple[bool, str]`（原因文本），驱动步骤可跳转与主按钮禁用原因；
  接口路径：第 1 步 = 设备列表非空且采样率可用；第 2 步 = SAFE-01 条件；第 3 步 = 就绪。DAW 路径：第 1 步 = 已导出或已指定参考；
  第 3 步 = 已选录音。
- 删除确认页里的“返回”（`ui/pages.py:964` 的 `back_button` 放到应用栏任务切换 / Esc）；
  `set_running` 时步骤 1–2 显示锁定。
- ⌘↩：主按钮文字变化后重新 `setShortcut`（准则 §12.2 实现提示）。
- 测试：960×640 下 `ActionBar.isVisible()` 且其 `geometry()` 在窗口内；步骤未完成时 `StepList` 对应项禁用并有 tooltip；
  ⌘↩ 在每一步触发主操作。

## 批次 2（P1）：图表可读性

| 顺序 | ID | 文件 / 部件 | 做法 | 状态 |
| --- | --- | --- | --- | --- |
| 2.1 | CHART-01 | `ui/design/tokens.py`（加 `series_1…8`、`band_1…8`、`plot_*`，按主题两列）、`ui/workspace.py:60-69`（`ENTRY_COLORS` 改存序号，颜色在绘制时按主题取）、`ui/theme.py:30`、`ui/views/decay.py:261` | 值见 SPEC §3.3；跑对比度脚本 | 【改现有】 |
| 2.2 | CHART-02 | `ui/views/frequency.py:207`、`ui/workspace.py:177-181`、其他调用 `DASHES` 的视图 | 线型按角色（当前 / 叠加 / 基准 / 原始），宽 2.0 / 1.25@80 % / 1.5 虚线 / 1.0@35 % | 【改现有】 |
| 2.3 | CHART-03 | `ui/plotkit.py:340, 461`、`LogFrequencyAxis` | 主次网格两层（自绘 `InfiniteLine` 或自定义 `AxisItem.tickValues` 返回两级）、0 dB 线 | 【改现有】 |
| 2.4 | CHART-04 | `ui/plotkit.py:284-289, 792-829` | 读数栏组件（新）：遍历可见 `Series` 插值；光标处多点标记；“显示值”注明 | 【需代码】；A/B 放置光标【需代码，后续】 |
| 2.5 | CHART-05 | `ui/components/context_bar.py`、`ui/views/frequency.py:98-118`、`ui/plotkit.py:set_title` | 删图内标题；“频响 / 差值”改为工具条布局切换（单 / 上下 / 并排） | 【改现有】 |
| 2.6 | CHART-06 | `ui/views/decay.py` | 拟合线、截断阴影、本底噪声线；数据取已存的 `DecayMetric`（不重算） | 【需代码】（GUI 显示层）；如果存档里没有拟合截距 → 【需 core / 单独 PR】，GUI 不得自行拟合 |
| 2.7 | CHART-07 | `ui/views/timefreq.py:538-560` | 透视默认关；选中切片用 `cursor`；色标；切片控件进工具条 | 【改现有】 |
| 2.8 | LAYOUT-01 | `ui/analysis_workspace.py`（任务栏 + `ContextBar` 合并为 `AppBar` 44 px）、`ui/main_window.py:201`（删 `QStatusBar`，`_set_place` 信息改进任务条 / 窗口标题） | SPEC §2.1、§5.1 | 【改现有】 |
| 2.9 | LAYOUT-02 | `ui/analysis_workspace.py:176`（视图下拉 → 分段标签，溢出“⋯”）；英文短标签进 `.po` | SPEC §8 | 【改现有】；新文案进 gettext |
| 2.10 | LAYOUT-03 | `ui/components/details_drawer.py`、`ui/design/tokens.py:13` | ≥ 1440 停靠（用 `QSplitter` 或布局插入）、以下覆盖；宽 220 / 288；状态写 `ui.ini` | 【改现有】 |
| 2.11 | COMPARE-01 | `ui/compare_view.py` | 双 `ChartPanel`（频响叠加 / 分频带 RT），`link_x` 已有（`ui/plotkit.py:624`）；判定表进检查器“对比”页；判定逻辑与文本不变 | 【改现有】 |
| 2.12 | FORM-01 | `ui/pages.py:875-937` 等 `QFormLayout` | `setFieldGrowthPolicy(FieldsStayAtSizeHint)` + 宽度 token；`FORM_WIDTH` 900 → 640 | 【改现有】 |

## 批次 3（P2）

| ID | 文件 | 做法 | 状态 |
| --- | --- | --- | --- |
| AI-01 | `ui/design/styles.py:36-38, 14`、`ui/views/overview.py` | GroupBox → 标题 + 分隔线；KPI 28；解读行去卡片 | 【改现有】 |
| TOOL-01 | `ui/components/tool_rail.py`、`ui/plotkit.py:830` | 工具并入图表工具条；V/H/Z/F | 【改现有】 |
| FMT-01 | `ui/pages.py:1062-1082` | 统一数值格式（`presentation/format.py` 尚不存在） | 【需代码】 |
| HIDPI-01 | `ui/components/tool_rail.py:14-16` | 按 `devicePixelRatioF()` 渲染图标 | 【改现有】 |
| MAC-01 | `locale/zh_CN/LC_MESSAGES/reverbscope.po:44-45` 等 | macOS 去助记符（运行时或分平台文案） | 【改现有】，需真机核对 |
| I18N-01 | 布局测试 | 断言按钮 `sizeHint` ≤ 宽度（zh / en × 960 / 1280 / 1440） | 【需代码】（测试） |
| THEME-01 | `ui/design/tokens.py` | 浅色 `plot_bg` 白、面板 `#f5f5f5`、输入边框 `border_strong` | 【改现有】 |
| ROOM-01 | `ui/room/view.py` | 默认平面 / 侧视 | 【维护者决定】 |
| DAW-01 | `core` 或 `io` 新纯函数 + GUI 显示 | 每声道峰值 | 【需 core / 单独 PR】 |
| — | 纵轴范围预设、电平框滚轮微调、⌘[ / ⌘] / ⌘B / ⌘E | | 【需代码】 |
| — | 实时输入电平表、测量中录音包络（`after/v2-02` 中标“未实现”） | 需要 worker 电平回调 | 【需 core / 单独 PR】，不做假数据 |

## 不要做

- 不改 `core/`、`models/`、`interpretation/`、`health.py`、音频后端、文件格式、CLI 输出、依赖（AGENTS.md）。
- 不把设计稿的演示数值当成验收数值。
- 不删除或放宽现有测试；行为变化（弹框 → 禁用）改断言并在 PR 说明。
- 不在 GUI 里做 DSP（拟合、峰值计算都从存档 / core 取）。

## 检查（每批）

`ruff check . && ruff format --check .`、`mypy --platform linux`、`python scripts/check_doc_links.py`、
`QT_QPA_PLATFORM=offscreen pytest`（覆盖率门槛 85 %），再用 `scripts/render_gui2_screenshots.py` 渲染 960 / 1280 / 1440 × zh / en ×
深 / 浅对照本规格；最后按 [REVIEW.md §6](REVIEW.md) 做真机交互 QA。
