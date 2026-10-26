# ReverbScope 专业桌面版 · 实现规格（给 Codex / Cursor / Claude）

> 状态：设计提案，待维护者确认。基线 `origin/main` @ `01291d8`（0.5.0b3）。
> 视觉规则见 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)，实现守则见 [AGENTS.md](AGENTS.md)。
> 本文的每个“现状”都在 main 源码里核对过，给出了文件和函数；“未实现”就是 main 里**没有**。

## 0. 范围

- **做**：窗口骨架（统一工具栏、列表、图表列、检查器、控制条）、响应式断点、token 扩展、字体、图表样式（两级网格、读数栏、图例条、光标）、组件状态、快捷键、普通/专业模式、布局切换。
- **不做**：任何分析算法、`core/`、`models/`、`io/`、`display/` 的数值逻辑；CLI；导出格式。图表只换“怎么画”，不换“画什么数”。
- **约束**：沿用 PySide6 Essentials + pyqtgraph 0.14.0（`ui/pg.py` 是唯一导入 pyqtgraph 的模块）；Fusion；不引入 QtCharts/QtGraphs；不引入 OpenGL。

## 1. 现状核对（main 01291d8）

| 方面 | main 现在是什么 | 位置 |
| --- | --- | --- |
| 窗口 | `MainWindow(QMainWindow)`，`setMinimumSize(960, 640)`，`resize(1366, 820)` | `ui/main_window.py` `MainWindow.__init__` |
| 三栏 | `QSplitter(Horizontal)`：`Navigator` \| `AnalysisWorkspace` \| `Inspector`；`setSizes([220, 860, 260])`；`navigator.setMinimumWidth(168)`、`inspector.setMinimumWidth(200)`；`setChildrenCollapsible(False)` | 同上 |
| 底部 | `MeasureStrip` 放在 splitter 下方（central widget 的 `QVBoxLayout`）；另有 `QStatusBar` | 同上；`ui/measure_strip.py` |
| 开合 | `set_navigator_open()` / `set_inspector_open()`，菜单动作 Ctrl+Shift+Left / Right；视图条上 `navigator_button`、`inspector_button`（`panelswitch` 属性） | `main_window.py`、`analysis_workspace.py` |
| 图表空间保护 | `_ensure_chart_space()`：中间 < 320 px 时 `reset_layout()` | `main_window.py` |
| 响应式 | **没有**窗口级断点；`MeasureStrip._reflow()` 在放不下时把控件改成上下两行 | `measure_strip.py` |
| 工具栏 | **没有** `QToolBar`、`QDockWidget`、`setUnifiedTitleAndToolBarOnMac` | — |
| 视图条 | `AnalysisWorkspace` 顶部一行 `viewtab` 按钮：概览·频率·时间·衰减·频谱（二级：声谱图/瀑布图/噪声）·房间·对比·报告；项目单独一个按钮 | `analysis_workspace.py` `VIEW_GROUPS` |
| 视图快捷键 | `NUMBERED_VIEWS` = overview, fr, etc, decay, noise, spectrogram, waterfall, room, project → Ctrl+1…9；compare → Ctrl+0 | 同上 |
| 图表 | `ChartPanel(QWidget)`：标题行（标题、适配、范围…、导出）、读数行、图例行（26 px 横向滚动）、`PlotWidget` | `ui/plotkit.py` |
| 交互 | 滚轮缩放（pyqtgraph 默认，两轴）；左键拖动平移；右键拖动框选（`ChartViewBox.mouseDragEvent`）；双击/R 适配；`AxisRangesDialog`；图例点击显示/隐藏；PNG/SVG/CSV 导出；`link_x()` | `plotkit.py`、`axis_ranges.py`、`pg.py` |
| 光标 | 悬停竖线 `cursor_line` + `cursor_dot`；读数只读**一条**曲线（`readout_series()`：标了 `readout` 的或最后一条） | `plotkit.py` `show_cursor`、`readout_text` |
| 网格 | `showGrid(x=True, y=True, alpha=0.28)`，一种颜色（`grid` token 给轴线） | `ChartPanel.restyle` |
| 对数轴 | `LogFrequencyAxis`：1-2-5 主刻度、其余次刻度；< 260 px 只标十倍程 | `plotkit.py` |
| 曲线色 | `ENTRY_COLORS`（8 个，按测量分配）；`DASHES` 线型；`curve_width()` 当前 2.4 / 基准 1.8 / 其他 1.15 | `ui/workspace.py`、`plotkit.py` |
| 频率响应 | 平滑下拉、对齐电平、原始曲线；上下分割的差值窗格（当前 − 基准） | `ui/views/frequency.py` |
| ETC | 能量时间曲线 / 波形；跨度 100/300/1000 ms/全部；搜索窗淡底；反射点可点；反射表（延迟、电平、多走路程、说明） | `ui/views/impulse.py` |
| 衰减 | 频带、指标下拉；上：Schroeder 曲线；下：分频带混响时间折线（`bands_chart`） | `ui/views/decay.py` |
| 分频带表 | 存在于概览视图（`tables.decay_table_rows`、`energy_table_rows`），**不在衰减视图** | `ui/tables.py`、`ui/views/overview.py` |
| 瀑布图 | 后台线程 `TransformWorker`；参数 窗/上升/步长/切片/平滑/透视；切片滑块；viridis；选中切片用 `tokens()["warn"]` | `ui/views/timefreq.py` |
| 声谱图、噪声、房间、项目、对比、报告 | 已有 | `ui/views/*`、`compare_view.py`、`project_view.py` |
| 检查器 | 单列滚动：测量健康、关键数据、条件、对比、所选反射、房间检查；分区标题 `title.upper()` | `ui/inspector.py` |
| 主题 | `LIGHT_TOKENS` / `DARK_TOKENS` 19 键；`stylesheet(t)`；`apply_application_chrome(app)`（Fusion + QPalette + QSS）；动态属性 `role`、`card`、`panel`、`viewbar`、`viewtab`、`panelswitch`、`strip`+`measuring`、`danger`、`primary`、`tone` | `ui/theme.py` |
| 字体 | 平台默认 UI 字体 + `CJK_FALLBACK_FONTS` 逐字回退（`install_cjk_ui_font`），13 px；**不打包字体** | `ui/theme.py` |
| 用户模式 | **没有**（`UserSettings` 只有 language、default_profile、theme、developer_tools…） | `settings.py` |
| 测量条 | 方式（音频接口 / DAW）、输入/输出设备、采样率、话筒/回采声道、位置、高级、设置…、开始（Ctrl+Return）、停止（`danger`，Esc 的 `QShortcut`）、阶段、进度 | `measure_strip.py` |
| 输入电平表 | **没有** | — |

## 2. 已实现 / 未实现矩阵

“画面”一列是设计稿里的标记：●=已实现（无徽章）；◐=已有数据或部件，需改样式/布局；○=未实现（设计稿带紫色“未实现”徽章或紫点）。

| 功能 | main | 画面 | 本规格阶段 |
| --- | --- | --- | --- |
| 三栏 + 底部测量条 | ● | 全部 | P1 改造 |
| 统一标题栏/工具栏、视图切换放进工具栏 | ○ | 全部 | P1 |
| 窗口断点、检查器浮层、列表图标栏 | ○（只有 `_ensure_chart_space`） | 08、09 | P1 |
| 新 token（plot_*、cursor、series_*、band_* …） | ○ | 全部 | P1 |
| 打包字体（Plex Sans / Mono、思源黑体） | ○ | 全部 | P1（需决策，§6） |
| 频率响应 + 差值上下布局 | ● | 01 | P2 换样式 |
| 两级网格、斜线区、0 线 | ◐ | 全部图 | P2 |
| 读数栏移到图下、列出每条可见曲线和 Δ | ◐（只读一条） | 01、05 | P2 |
| 图例条（色条 + 角色 + 处理说明） | ◐（图例芯片已有） | 全部图 | P2 |
| ETC + 反射表 | ● | 02 | P2 换样式 |
| 放置光标 A/B + Δ（时间、电平、声程差） | ○ | 02、10 | P3 |
| 指针工具（平移/框选/光标）分段按钮 | ○（右键框选已有） | 全部图 | P3 |
| 滚轮只缩横轴、⇧ 缩纵轴 | ○ | — | P3 |
| 衰减 + 分频带图 | ● | 03 | P2 换样式 |
| 分频带数据表放进衰减视图 | ◐（`decay_table_rows` 已有） | 03 | P2 |
| 不可靠值：空心点、不连线、“(x)?” | ◐（视图里有效性已区分；画法统一为新） | 03 | P2 |
| 瀑布图 | ● | 04 | — |
| 瀑布图切片遮挡填充、选中切片用 `cursor` 色 | ○ | 04 | P2 |
| 布局切换：单图 / 上下 | ◐（上下只在频率、衰减、ETC 里固定存在） | 01–05 | P3 |
| 布局切换：并排双图 | ○ | 05 | P3 |
| 叠加、基准、对比判定 | ● | 01、05 | — |
| 检查器分标签页（检查 / 参数 / 对比） | ◐（分区已有，标签页新） | 01–05 | P2 |
| 测量列表 T30 列、质量图标 | ◐（两列树，标记文字） | 全部 | P2 |
| 普通 / 专业模式 | ○ | 06 | P4 |
| 测量中：设置锁定摘要、进行中横幅 | ◐（`measuring` 属性、阶段、进度已有） | 07 | P2 |
| 实时输入电平表 | ○ | 07 | P4（需要音频层支持，另立任务） |
| 组件状态（悬停/按下/禁用/焦点/开启） | ◐（部分 QSS） | 10 | P1 |

## 3. 布局树 → Qt 控件

```
MainWindow(QMainWindow)                        # 现有
├── QMenuBar（macOS 原生）                       # 现有 _build_menus()
├── QToolBar "mainToolbar"  [新]  addToolBar(Top); setMovable(False); setFloatable(False)
│   │   macOS: setUnifiedTitleAndToolBarOnMac(True)；高 52
│   ├── QToolButton navigator_toggle  (panel-left, ⇧⌘←)          # 由 navigator_action 驱动
│   ├── TitleBlock(QWidget)  [新]  测量名（window_title）+ 房间·采样率·时间（caption），各自省略号
│   ├── stretch
│   ├── ViewSwitcher(QWidget)  [新]  QButtonGroup 分段按钮，顺序 = NUMBERED_VIEWS[:7] + “⋯”菜单（房间、项目、对比、报告）
│   ├── stretch
│   ├── Badge "synthetic" / "measuring"
│   ├── ModeSwitch(普通|专业)  [新，P4]
│   └── QToolButton inspector_toggle  (panel-right, ⇧⌘→)
├── centralWidget: QWidget(QVBoxLayout, margins 0, spacing 0)      # 现有
│   ├── ResponsiveSplitter(QSplitter Horizontal)  [改]  handleWidth 1
│   │   ├── Navigator  [改]  宽 220；rail 模式 48（MeasurementRail，同一模型）
│   │   ├── AnalysisWorkspace  [改]  删掉顶部 viewtab 行（移到工具栏）；保留 QStackedWidget
│   │   │   └── 每个 AnalysisView
│   │   │       ├── ChartToolBar(QWidget 34)  [新，替换各视图自己的 controls QHBoxLayout]
│   │   │       ├── LegendStrip(24)          [改自 ChartPanel.legend_area]
│   │   │       ├── ChartLayout(QSplitter Vertical/Horizontal)  [新]  单 / 上下 / 并排
│   │   │       │   ├── ChartPanel 主图（无标题行）
│   │   │       │   └── PaneHeader(22) + ChartPanel 或 DataTable 副图
│   │   │       └── ReadoutBar(24)            [改自 ChartPanel.readout]
│   │   └── Inspector  [改]  宽 288；顶部 QTabBar（检查/参数/对比）+ QStackedWidget
│   └── MeasureStrip → ControlBar  [改]  高 44；吸收 QStatusBar 的状态文字
├── InspectorOverlay(QFrame)  [新]  W < 1280 时 Inspector 被 reparent 到这里，浮在图表列右侧，带阴影
└── QStatusBar  [改]  setVisible(False)；消息改由 ControlBar.status 显示（showMessage 包一层）
```

说明：

- **不用 `QDockWidget`**：dock 的标题栏、浮动、拖拽停靠会带来非 macOS 的外观和难测的状态；现有 splitter 方案已经稳定，测试也基于它（`tests/ui/test_workstation_polish.py`）。检查器浮层用一个普通的子 `QFrame` 叠在 central widget 上。
- **视图切换移到工具栏**：`AnalysisWorkspace.buttons` / `group` 的逻辑搬到 `ViewSwitcher`，`view_chosen` 信号不变，`MainWindow.show_view()` 不变。二级选择器 `subview` 删除——专业模式里 噪声 / 声谱图 / 瀑布图 直接是一级（顺序与 Ctrl+5/6/7 一致）。
- **ChartPanel 拆头**：`ChartPanel` 的标题行（`title`、`reset_button`、`axes_button`、`export_button`）和 `readout` 移到视图级的 `ChartToolBar` / `ReadoutBar`；`ChartPanel` 保留 `plot`、`legend`、所有方法。为兼容，保留属性名（`chart.reset_button` 等指向工具条里的按钮）。

## 4. 尺寸、断点、折叠

### 4.1 常量（`ui/layout.py`，新文件）

```python
TOOLBAR_H = 52; CHARTBAR_H = 34; LEGEND_H = 24; PANE_HEADER_H = 22; READOUT_H = 24; CONTROLBAR_H = 44
LIST_W = 220; LIST_W_WIDE = 248; LIST_MIN = 200; LIST_MAX = 320; RAIL_W = 48
INSPECTOR_W = 288; INSPECTOR_W_WIDE = 340; INSPECTOR_MIN = 264; INSPECTOR_MAX = 400
CHART_MIN_W = 640; CHART_MIN_H = 320; CHART_SHARE_MIN = 0.60; CHART_DOCK_MIN = 720
BP_WIDE = 1680; BP_INSPECTOR = 1280; BP_RAIL = 1024; WINDOW_MIN = (960, 640)
BP_SHORT = 760   # 高度
CONTROL_H = 24; TOOL_H = 26; SEG_H = 22; ROW_H = 24; TABLE_ROW_H = 22
```

（准则 §13.1 要求像素尺寸只出现在 `ui/design/` 里；在 `ui/design/` 建立之前先放 `ui/layout.py`，Phase 2 一起搬。）

### 4.2 算法（`MainWindow.resizeEvent` → `_apply_breakpoints(width, height)`）

```python
def _apply_breakpoints(self, w: int, h: int) -> None:
    list_w = self.navigator.width() if self._list_user_w else (LIST_W_WIDE if w >= BP_WIDE else LIST_W)
    insp_w = self.inspector_width_pref or (INSPECTOR_W_WIDE if w >= BP_WIDE else INSPECTOR_W)
    rail = w < BP_RAIL
    self.navigator.set_rail(rail)                       # 48 px，只显示色条 + 短名
    left = RAIL_W if rail else list_w
    can_dock = w >= BP_INSPECTOR and (w - left - insp_w - 2) >= max(CHART_DOCK_MIN, CHART_SHARE_MIN * w)
    if self._inspector_user_closed:
        mode = "closed"
    elif can_dock:
        mode = "docked"
    else:
        mode = "overlay-hidden" if self._inspector_mode != "overlay-open" else "overlay-open"
    self._set_inspector_mode(mode)
    self.chart_toolbar_compact = 0 if w >= BP_INSPECTOR else 1 if w >= BP_RAIL else 2
    self.strip.set_compact(self.chart_toolbar_compact)
    self.toolbar.set_compact(self.chart_toolbar_compact)
    self.workspace.set_short(h < BP_SHORT)
```

- 默认宽度下 `can_dock` 在 W ≥ 1280 时为真（1280 − 220 − 288 − 2 = 770 ≥ 0.6 × 1280 = 768）；第二个条件只在用户把列表或检查器拖宽时起作用。
- 断点穿越用 120 ms 去抖（`QTimer.singleShot`），避免拖窗口边时反复重排。
- `_inspector_user_closed`：用户点了关闭（✕ / ⇧⌘→ / 菜单）为真，用户再次打开为假；**自动隐藏不改它**。写入 `ui_state`（`window/inspector` 现有键；新增 `window/inspector_mode`）。
- `_ensure_chart_space()` 保留，阈值从 320 改为 `CHART_MIN_W`。
- 浮层：`InspectorOverlay` 宽 `insp_w`，高 = 图表列高，右对齐，阴影 token；Esc 或点浮层外关闭；打开/关闭 180 ms 动画（减少动态效果时 0）。

### 4.3 折叠后各部件

| compact | 工具栏 | 图表工具条 | 控制条 |
| --- | --- | --- | --- |
| 0（≥ 1280） | 标题块 200；视图 7 项 | 全部文字 | 全部 |
| 1（1024–1279） | 标题块 150 | “对齐电平”保留，“原始曲线”收进 `显示选项…` popover | 去掉 输出、扫频摘要、“上次…” |
| 2（< 1024） | 标题块 120；视图 4 项 + “⋯”；“合成演示数据”→“合成” | 文字按钮变图标（适配、导出）；频率刻度稀疏 | 只留 开始/停止、方式、采样率、位置、“…” |

## 5. Token 扩展（`ui/theme.py`）

1. 在 `LIGHT_TOKENS` / `DARK_TOKENS` 末尾追加 DESIGN_SYSTEM §1.2 的全部新键（值逐字复制）。**现有 19 个键不改值**。
2. `PLOT_SERIES`（matplotlib，6 色）保持给静态导出用；新增 `def series_color(index: int) -> str: return tokens()[f"series_{index % 8 + 1}"]`。`ui/workspace.py` 的 `ENTRY_COLORS` 改为在 `_next_color()` 里调用 `series_color()`（主题切换时 `restyle` 重新取色）。
3. 新增 `def band_color(index: int) -> str`（`band_1…8`）。
4. `stylesheet(t)` 新增选择器（只用动态属性，不用 objectName）：
   - `QToolBar#mainToolbar { background: toolbar; border-bottom: 1px solid border; spacing: 6px; }`
   - `QWidget[chartbar="true"] { background: surface; border-bottom: 1px solid border; }`
   - `QWidget[readout="true"] { background: readout_bg; border-top: 1px solid border; }`
   - `QWidget[sidebar="true"]`、`QWidget[inspector="true"]`（`panel` 底）、`QFrame[overlay="true"]`
   - `QToolButton[tool="true"]` 及 `:hover`、`:pressed`、`:checked`、`:disabled`、`:focus`
   - `QToolButton[segment="true"]`、`QWidget[segmented="true"]`
   - `QPushButton:focus { border: 2px solid focus; }`（全局焦点环，替换边框，尺寸不变：`padding` 减 1）
   - `QFrame[badge="planned|synthetic|status"]`、`QFrame[banner="info|warn|bad"]`
   - `QTreeWidget[measurements="true"]::item { height: 24px; } ::item:selected { background: selected; color: text; }`
   - `QTableView[dense="true"]`（行高 22、隔行 `readout_bg`、无网格线、表头 `label` 字）
5. `apply_application_chrome()`：`QPalette.Highlight` 改为 `selected`、`HighlightedText` 改为 `text`（列表选中不再整行实心青色），`PlaceholderText` 改为 `faint`。
6. 新增测试 `tests/unit/test_theme_tokens.py`：两个字典键集合相同；所有值是 `#rrggbb`；运行 DESIGN_SYSTEM §1.5 的 162 对对比度（把 `contrast_pro.py` 的表搬进测试），全部通过。

## 6. 字体

| 选项 | 内容 | 体积（安装包增加） | 备注 |
| --- | --- | --- | --- |
| **F1（推荐）** | 打包 IBM Plex Sans 400/500/600 + IBM Plex Mono 400/500/600（原文件，不改名）；中文用平台字体回退（`CJK_FALLBACK_FONTS`：苹方 / 微软雅黑 / Noto CJK） | 约 1.1 MB | 拉丁和数字三平台一致；不碰 OFL 保留名；中文观感随平台 |
| F2 | F1 + 思源黑体 CN 子集（GB2312 + 标点，约 7900 码位），**必须改内部名**（如 “RS Sans CJK”）并附 OFL | 约 +8–10 MB（3 个字重） | 三平台完全一致；符合用户选择的 A2 中文部分 |
| F3 | F1 + 思源黑体 CN 原文件（不改名） | 约 +25 MB | 最简单，体积大 |

实现（任一选项）：

- 字体文件放 `src/reverbscope/assets/fonts/`，`hatch_build.py` / `packaging/reverbscope.spec` 的数据文件里加上；许可证原文放同目录 `OFL.txt`，`NOTICE` 和 `docs/DEPENDENCIES.md` 登记。
- `theme.install_cjk_ui_font(app)` 改为 `install_ui_fonts(app)`：`QFontDatabase.addApplicationFont()` 逐个加载；`app.setFont()` 的 families = `["IBM Plex Sans", "Source Han Sans CN"(F2/F3), *CJK_FALLBACK_FONTS]`，像素 13。
- 新增 `theme.mono_font(px=12, weight=400) -> QFont`，families = `["IBM Plex Mono", 中文回退…]`；`apply_report_font()` 改用它。
- 数字控件统一走 `mono_font`：`AxisItem.setTickFont`、读数栏、表格数字列（委托里 `QStyleOptionViewItem.font`）、检查器数值标签、列表 T30 列。
- 准则 D9 需要改写（见 DESIGN_SYSTEM §0.3）。

## 7. 图表实现（`ui/plotkit.py`）

### 7.1 外观

1. `ChartPanel.restyle()`：`setBackground(t["plot_bg"])`；`showGrid(False, False)`；轴 `setPen(plot_axis)`、`setTextPen(plot_text)`、`setTickFont(mono_font(11))`、`setStyle(tickLength=-4, tickTextOffset=4)`；显示 top/right 轴（无刻度值）形成边框。
2. 新类 `ChartGrid(pg.GraphicsObject)`：挂在 ViewBox 里，`ignoreBounds=True`，`zValue=-30`；在 `sigRangeChanged` 时按当前轴的 `tickValues()` 取两级刻度，`paint()` 里用 `plot_grid_minor` 画次级、`plot_grid_major` 画主级、`plot_zero` 画 0 线（cosmetic pen 1 px）。一个对象画全部网格，不为每条线建 `InfiniteLine`。
3. dB 轴新类 `LevelAxis(pg.AxisItem)`：`tickValues` 返回 `[(10, major), (2 或 5, minor)]`（范围 > 60 dB 用 5）；`tickStrings` 用 U+2212。
4. `add_excluded(x0, x1, label)`：斜线区（`plot_excluded`，`Qt.BDiagPattern`），左下角 `caption` 文字。频率响应、差值、声谱图在扫频范围外调用；衰减在 `truncation_time_s` 之后调用。
5. `curve_width()`（`ui/workspace.py`）：当前 2.2、基准 1.8、叠加 1.6；叠加 `alpha 0.9`；基准 `DASHES[1]`。

### 7.2 读数栏与图例条

- 新类 `ReadoutBar(QWidget)`（`readout=true`，24 px）：`set_segments([(text, color_token)], hint="")`。
- `ChartPanel.readout_text()` 扩展为 `readout_segments(plot_x)`：x 文本 + **每条可见曲线**的 `value_at()`（用曲线颜色）+ 恰好两条可见时的 `Δ`。仍然注明“显示值”。`readout_hook`（声谱图、瀑布图）保持优先。
- `LegendStrip`：沿用 `_rebuild_legend()` 的芯片，改成 色条（含线型，`swatch_icon()` 已有）+ 名称 600 + 角色（当前 / 基准）；右侧 `set_note(text)` 写显示处理（“显示平滑 1/6 oct”）。

### 7.3 放置光标（未实现 → P3）

```python
class CursorPair(QObject):                 # plotkit.py
    changed = Signal()
    def __init__(self, chart: ChartPanel): ...
    def place(self, which: str, plot_x: float) -> None    # "A" | "B"
    def clear(self) -> None
    def values(self) -> dict                               # 每条可见曲线在 A、B 处的值、Δx、Δy
```

- 每个光标 = `pg.InfiniteLine(movable=True)`（`cursor` 色，A 实线 B 虚线）+ 旗标 `pg.TextItem`（`cursor` 底）+ 曲线交点空心 `ScatterPlotItem`。
- 放置：光标工具下单击；或任意工具下 C 键放在悬停位置（先 A 后 B，第三次移动最近的那个）；⇧C 清除；⇧ 拖动吸附到 ±8 px 内的局部极值（在 `Series.y` 上找，不重新分析）。
- 读数：读数栏切换为 `A …│ B …│ Δ …`；视图可以加派生量：ETC 加 `Δpath = Δt · c`（c 取 `result.placement.speed_of_sound_m_s`，现有字段），频率响应加 `Δf` 的倍频程数。
- 状态按视图、按测量记在 `ui_state`（与手动范围一样）。

### 7.4 指针工具与滚轮

- `ChartToolBar` 左侧三段：平移（默认）/ 框选 / 光标。框选模式下左键拖动 = 现有右键框选逻辑（`ChartViewBox.mouseDragEvent` 增加 `mode`）。
- `ChartViewBox.wheelEvent`：默认只缩 x（`axis=0`），⇧ 时只缩 y，⌥ 时两轴；这是对现有行为的改变，要在 CHANGELOG 写明。

### 7.5 布局切换（P3）

- 新 `ChartLayout(QWidget)`：`set_mode("single" | "stacked" | "side")`，内部一个 `QSplitter`，切换时改方向，不重建 `ChartPanel`。
- 上下（现有）：频率响应 = 主图 + 差值；ETC = 主图 + 反射表；衰减 = Schroeder + 分频带图 + 分频带表（三段）。
- 并排（新）：右窗格有自己的视图下拉（`PaneHeader` 里），内容用另一个视图类的“窗格模式”（只画图，不带工具条）；两窗格共用 `WorkspaceModel` 的叠加集合；“联动光标”勾选时横轴同为频率的两个窗格同步悬停位置。只有横轴单位相同的两个窗格才 `link_x()`。

### 7.6 各视图改动

| 视图 | 改动 |
| --- | --- |
| `views/frequency.py` | 控件行 → `ChartToolBar`（平滑、对齐电平、原始曲线）；扫频范围外 `add_excluded`；差值窗格加 `PaneHeader`（“差值 · B-1 − A-1”）；y 默认 −20…+30（或中位数 ±25，取整到 10） |
| `views/impulse.py` | 控件 → `ChartToolBar`；阈值线标注；反射编号 `#n`；表格改 `DataTable`（dense）；光标 A/B（P3），派生声程差 |
| `views/decay.py` | 频带曲线用 `band_color()`；宽带 `text` 2.0；评估范围虚线 + 文字；截断后斜线；分频带图：T30 实线圆、T20 虚线方、EDT 点线三角，无效值空心点 + “?” 且 `connect="finite"`（把无效值置 NaN）；新增第三窗格 `DataTable`，行来自 `tables.decay_table_rows()` + `energy_table_rows()`（不新增计算） |
| `views/timefreq.py` | 瀑布图：`add_curve(..., fill_level=floor+dy, brush=plot_bg)`（需要 `ChartPanel.add_curve` 支持 `fillLevel`）；选中切片 `tokens()["cursor"]` 代替 `warn`；色条图例 |
| `views/noise.py`、`views/overview.py`、`views/report.py` | 只换 token、字体、网格 |

## 8. 组件状态（QSS 要点）

见 DESIGN_SYSTEM §7.1 的表。实现规则：

- 用 Qt 伪状态（`:hover`、`:pressed`、`:disabled`、`:focus`、`:checked`）；不要用 `state` 属性（设计稿里的 `state` 只是为了静态出图）。
- 焦点环 2 px 替换 1 px 边框时 `padding` 少 1 px，避免控件跳动。
- 列表、表格选中行用 `selected` 底 + `text` 字（不再用实心强调色）。
- 测试：`tests/ui/test_states.py` 离屏抓取每种组件 × 6 状态 × 浅/深，像素采样断言背景色等于 token（容差 2）。

## 9. 快捷键

| 动作 | macOS | Win/Linux | 现状 |
| --- | --- | --- | --- |
| 新测量 / 打开测量 / 打开项目 / 保存 | ⌘N / ⌘O / ⇧⌘O / ⌘S | Ctrl+… | 已有 |
| 对比 / 设置 / 退出 | ⇧⌘C / ⌘, / ⌘Q | | 已有 |
| 视图 概览…瀑布图、房间、项目 | ⌘1…⌘9 | Ctrl+1…9 | 已有（顺序与工具栏一致） |
| 对比视图 | ⌘0 | Ctrl+0 | 已有 |
| 显示/隐藏 列表 / 检查器 | ⇧⌘← / ⇧⌘→ | Ctrl+Shift+←/→ | 已有；窄窗时 ⇧⌘→ 打开浮层（新） |
| 音频接口 / DAW 设置页 | ⇧⌘1 / ⇧⌘2 | | 已有 |
| 开始测量 | ⌘↩ | Ctrl+Enter | 已有 |
| 停止并静音 | Esc | Esc | 已有 |
| 适配图表 | R、双击 | | 已有 |
| 筛选测量 | ⌘F | Ctrl+F | 新 |
| 单图 / 上下 / 并排 | ⌥⌘1 / ⌥⌘2 / ⌥⌘3 | Ctrl+Alt+1/2/3 | 新 |
| 平移 / 框选 / 光标 工具 | H / Z / C（图表获得焦点时） | 同 | 新 |
| 放置光标（悬停处）/ 清除 | C / ⇧C | 同 | 新 |
| 导出图表 PNG / 曲线 CSV | ⌘E / ⇧⌘E | Ctrl+E / Ctrl+Shift+E | 新（动作已有，快捷键新） |
| 普通 / 专业 模式 | ⇧⌘P | Ctrl+Shift+P | 新（P4） |
| 列表：上一条 / 下一条；叠加；设为基准 | ↑ / ↓；空格；B | 同 | ↑↓ 已有（QTreeWidget）；空格、B 新 |

单键快捷键只在图表或列表有焦点时生效（`Qt.WidgetWithChildrenShortcut`），不与文本输入冲突。

## 10. 普通模式与专业模式

设置新增 `UserSettings.ui_mode: str = ""`（`""` = 按用户类型决定；`"guided"` / `"pro"`），以及 `user_type: str = ""`（`everyday` / `musician` / `pro`，来自首次启动的选择，已在设计里定稿）。`schema_version` 不变（新增键有默认值；旧版本读到新键时 `UserSettings.from_dict` 的 `drop_unknown` 会丢掉它）。在 `from_dict` 里像 `theme`、`cli_style` 一样，把不在允许集合里的值回退成 `""`。

| 方面 | 普通（guided） | 专业（pro） |
| --- | --- | --- |
| 默认给谁 | 普通用户 | 音乐人（措辞混合）、专业人士 |
| 视图切换 | 结论 / 频率 / 混响 / 反射（4 个；映射到 overview、fr、decay、etc） | 概览 / 频率响应 / ETC / RT60 / 噪声 / 声谱图 / 瀑布图 + ⋯（房间、项目、对比、报告） |
| 图表工具条 | 一句“这张图说明什么” + 显示上次 + 适配 + 导出 | 指针工具、视图参数、布局、适配、范围、导出 |
| 网格 | 只画主网格 | 主 + 次网格 |
| 图上注释 | 编号注释（共振、反射），点击跳到检查器对应条目 | 无注释，靠检查器“检测到” |
| 读数栏 | 一句话（“指着 110 Hz：这次 +16.1 dB · 上次 +25.4 dB”） | 分段 Mono 读数，光标 A/B |
| 检查器 | “解读 / 帮助”：测量怎么样 → 房间的三件事 → 下一步 | “检查 / 参数 / 对比”：测量质量、关键数据、检测到、显示与分析参数、对比表 |
| 列表 | 名称 + 质量图标 | 名称 + 基准 + T30 + 质量图标；列头 |
| 控制条 | 开始测量 + 一行设置摘要 + 更改… | 全部设备、采样率、扫频摘要、位置、设置… |
| 数据表 | 不显示 | 衰减视图第三窗格、ETC 反射表 |
| 布局切换 | 不显示（单图） | 单 / 上下 / 并排 |
| 措辞 | `interpretation` 的通俗说法（`register=plain`） | 术语（RT60、T30、C50…），注脚写方法 |
| 参数 | 只有平滑（3 档） | 全部（瀑布图的窗/上升/步长…） |

切换模式不改变选中的测量、叠加集合和图表范围。

## 11. 逐文件改动计划

| 文件 | 改动 | 阶段 |
| --- | --- | --- |
| `src/reverbscope/ui/theme.py` | 新 token 键；`series_color()`、`band_color()`；`stylesheet()` 新选择器；`apply_application_chrome()` 调色板；`install_ui_fonts()`、`mono_font()` | P1 |
| `src/reverbscope/ui/layout.py`（新） | §4.1 常量 | P1 |
| `src/reverbscope/assets/fonts/`（新） | 字体文件 + OFL.txt（按 §6 的选项） | P1 |
| `hatch_build.py`、`packaging/reverbscope.spec`、`packaging/pyinstaller_filters.py` | 打包字体 | P1 |
| `src/reverbscope/ui/main_window.py` | `QToolBar` + `setUnifiedTitleAndToolBarOnMac(True)`；`resizeEvent` → `_apply_breakpoints`；`InspectorOverlay`；状态栏隐藏并转发；`reset_layout()` 用 `LIST_W`/`INSPECTOR_W`；`_ensure_chart_space()` 用 `CHART_MIN_W`；新快捷键 | P1 |
| `src/reverbscope/ui/toolbar.py`（新） | `TitleBlock`、`ViewSwitcher`（从 `analysis_workspace.py` 搬 `VIEW_GROUPS` 逻辑）、`ModeSwitch` | P1 |
| `src/reverbscope/ui/analysis_workspace.py` | 去掉顶部按钮行与 `subview`；保留 `stack`、`views`、`show_view`、`current_view_id`、`view_chosen`；`navigator_button`/`inspector_button` 改为指向工具栏按钮（兼容属性） | P1 |
| `src/reverbscope/ui/navigator.py` | 行高 24；第 2 列改为 T30（Mono，右对齐）+ 质量图标；`set_rail(bool)`；`⌘F` 筛选框；空格叠加、B 基准 | P2 |
| `src/reverbscope/ui/inspector.py` | 顶部 `QTabBar`（检查/参数/对比）；分区标题不再 `upper()`；键值行 = 标签 + Mono 值 + 单位列；“检测到”分区（共振、交流声、反射，数据来自现有 `result`）可点击定位 | P2 |
| `src/reverbscope/ui/measure_strip.py` | 高 44；`set_compact(level)` 代替/补充 `_reflow`；测量中把设置控件替换为一行锁定摘要；吸收状态文字 | P2 |
| `src/reverbscope/ui/plotkit.py` | `ChartGrid`、`LevelAxis`、`add_excluded`、`ReadoutBar`、`LegendStrip`、`readout_segments`、`add_curve(fill_level=)`；拆掉标题行（兼容属性）；P3：`CursorPair`、指针工具、`wheelEvent`、`ChartLayout` | P2/P3 |
| `src/reverbscope/ui/chartbar.py`（新） | `ChartToolBar`、`PaneHeader`、`LayoutSwitch` | P2 |
| `src/reverbscope/ui/views/frequency.py`、`impulse.py`、`decay.py`、`timefreq.py`、`noise.py` | §7.6 | P2 |
| `src/reverbscope/ui/workspace.py` | `ENTRY_COLORS` → `series_color()`；`curve_width()` 新值 | P2 |
| `src/reverbscope/ui/tables.py` | 不改计算；新增 `DenseTableModel`（`QAbstractTableModel`）供衰减/ETC/对比表复用 | P2 |
| `src/reverbscope/settings.py` | `ui_mode`、`user_type` 两个键（默认 `""`） | P4 |
| `src/reverbscope/ui/settings_dialog.py` | “界面模式”分段控件 | P4 |
| `src/reverbscope/locale/*` | 新字符串（中文为主，英文同步） | 各阶段 |
| `docs/GUIDELINES.zh-CN.md` | D9、§13.4–13.6、§13.9、§15.2 按 DESIGN_SYSTEM §0.3 修订（维护者确认后） | P0 |
| `scripts/render_gui2_screenshots.py` | 加 1440×900、1100×720、960×640 三档 | P1 |

**不改**：`core/`、`display/`（瀑布图遮挡只在 `ui/` 画）、`models/`、`io/`、`cli/`、`interpretation/` 的逻辑。

## 12. 分阶段任务、验收与测试

每阶段一个 PR，标题按准则：“§13 P1: …”。每个 PR 附 1440×900 / 1100×720 / 960×640 × 浅/深 × 中/英 的离屏截图（`scripts/render_gui2_screenshots.py`）。

### P0 · 决策（维护者，无代码）

- 确认 DESIGN_SYSTEM §0.3 的 7 项差异；选字体选项 F1/F2/F3；确认 D7（Lucide）。
- **验收**：附录 F 勾选；GUIDELINES 修订合并。

### P1 · 骨架、token、字体、断点

任务：§5 token；§6 字体；`ui/layout.py`；工具栏 + 视图切换；断点算法 + 检查器浮层 + 列表图标栏；状态栏转发；组件状态 QSS；新快捷键（⌘F、⌘E、⇧⌘E）。

验收：
1. 1440×900：列表 220、检查器 288，图表列宽 ≥ 0.60 × 窗口宽（930 px）。
2. 宽度从 1440 拖到 960：W < 1280 时检查器自动隐藏，⇧⌘→ 以浮层打开且图表宽度不变；W < 1024 时列表变 48 px 图标栏；任何时刻图表列 ≥ 640 px。拖回 1440 时倒序恢复；用户手动关闭的检查器不自动打开。
3. macOS 上工具栏与标题栏合一；菜单栏为原生；所有快捷键在 Windows/Linux 显示为 Ctrl。
4. `contrast` 测试 162 对全部通过；两个 token 字典键集合相同。
5. 中文、英文下工具栏、控制条在 960 宽时无截断（文本省略号允许出现在标题块和设备名）。

测试（新增/修改）：
- `tests/unit/test_theme_tokens.py`（键集合、hex 格式、对比度）。
- `tests/ui/test_breakpoints.py`：`window.resize(w, 800)` 遍历 [1680, 1440, 1279, 1100, 1023, 960]，断言 `inspector_mode`、`navigator.is_rail()`、`splitter.sizes()[1] >= CHART_MIN_W`、`>= 0.6*w`（≥1280 时）。
- `tests/ui/test_workstation_polish.py`：把 `>= 320` 改为 `>= CHART_MIN_W`；`set_inspector_open(False)` 后缩放窗口不得重新打开。
- `tests/ui/test_gui_zh.py`：工具栏视图名中文。
- 字体：`QFontDatabase.families()` 含 “IBM Plex Sans”“IBM Plex Mono”；`mono_font().family()` 正确。

### P2 · 图表样式、读数、检查器、列表、控制条

任务：§7.1、§7.2、§7.6；检查器标签页；列表 T30 列；控制条测量中锁定摘要；衰减视图数据表；瀑布图遮挡与选中色。

验收：
1. 频率响应：扫频范围外斜线；主/次网格颜色等于 token；0 dB 线 1.2 px；刻度 Plex Mono 11。
2. 读数栏列出全部可见曲线的值与 Δ（两条时），颜色与曲线一致；数值与 `value_at()` 一致（显示值）。
3. 衰减视图出现第三窗格数据表，数值与 `reverbscope show` 输出逐格相同（同一 `result.json`）；不可靠值显示 `(x.xx)?` 且悬停显示 `reason`。
4. 分频带图：不可靠点空心、不连线。
5. 瀑布图：后面的切片被前面的遮挡；选中切片不再是 `warn` 色。
6. 测量中：控制条只剩开始（禁用）、停止、锁定摘要、阶段、进度；Esc 停止；切换视图不中断（现有测试 `test_gui_lifecycle` 继续通过）。

测试：
- `tests/ui/test_views.py`：每个视图的 `ChartPanel` 有 `ChartGrid`；`showGrid` 关闭；`plot_bg` 背景。
- `tests/ui/test_readout.py`：两条曲线 + 已知 x，断言分段文本。
- `tests/ui/test_decay_table.py`：表格行 = `decay_table_rows(result)`。
- `tests/ui/test_timefreq_state.py`：选中切片颜色 = `cursor`。
- 截图对比（人工评审）：`screens/01–04、07` 对应画面。

### P3 · 光标、指针工具、布局切换

任务：§7.3、§7.4、§7.5；⌥⌘1/2/3；H/Z/C；C/⇧C。

验收：
1. ETC：放 A 于直达声、B 于 9.29 ms 反射，读数栏显示 `Δt 9.29 ms`、`ΔL −14.5 dB`、`声程差 3.19 m`（c = 343.2 m/s，来自 `result.placement`）。
2. ⇧ 拖动吸附到局部极值；光标状态按视图、按测量记住，重启后恢复。
3. 滚轮默认只缩横轴；⇧ 缩纵轴；⌥ 两轴。
4. 并排布局：右窗格可选 RT60/ETC/频率响应；同单位横轴联动；切换布局不重建图表（`ChartPanel` 对象 id 不变）。

测试：`tests/ui/test_cursors.py`（`CursorPair.values()` 数值、键盘放置、清除）；`tests/ui/test_chart_layout.py`（三种模式切换、`link_x` 只在同单位时建立）；`tests/unit/test_pg.py` 里禁止 `import pyqtgraph` 的规则继续通过。

### P4 · 普通 / 专业模式（以及另立任务的电平表）

任务：§10；设置项；工具栏 ModeSwitch；普通模式视图集、检查器“解读”、注释、控制条摘要。

验收：普通用户首次启动进入普通模式；⇧⌘P 切换不丢选择和范围；普通模式无指针工具、无布局切换、无数据表；所有数字仍来自 `result`（解读文字来自 `interpretation`，不在 UI 里新写判断）。

测试：`tests/ui/test_modes.py`（两种模式下可见控件集合）；`tests/unit/test_settings.py`（新键默认值、非法值回退）。

**实时输入电平表**不在本规格内实现：需要 `audio/` 在播放/录音时提供电平回调，属于音频层改动，按准则另立任务；P2 只预留控制条位置。

## 13. 开放问题

1. **字体**：F1 / F2 / F3 选哪个？F2 需要做子集并改名（OFL 保留名 “Source”），F3 安装包 +25 MB。D9 要不要正式改写？
2. **D7 Lucide** 还没在附录 F 勾选；本设计依赖它（约 30 个图标）。
3. **专业模式默认给音乐人**是否合适，还是音乐人默认普通模式、措辞混合？
4. **滚轮行为改变**（只缩横轴）会改变老用户习惯，是否接受，或者做成设置项？
5. **并排布局**右窗格允许哪些视图？建议只允许有图的视图（不含概览、报告、房间）。
6. **状态栏**合并进控制条后，开发者模式里的长消息放哪？建议放控制条状态文字的悬停提示 + “复制详细信息”。
7. **断点阈值** 1280 / 1024 是按默认宽度推出来的；如果用户把检查器拖到 400，检查器会在 W < 1555 时就收起（W − 220 − 400 − 2 ≥ 0.6 W）——这是规则使然，需要确认可以接受。
8. 与准则 §13.5 “≥ 1440 推开抽屉”的写法冲突，需要在 GUIDELINES 修订里统一。
9. 实现 P2/P3 时，把新借鉴的通用惯例（两级网格、放置光标 A/B 与 Δ 读数、并排双图、瀑布图遮挡）登记到 `docs/design/GUI_REFERENCE_AUDIT.md`（只借鉴思路，不涉及任何资产）。本次设计提交没有改那个文件。
