# 给实现者（Codex / Cursor / Claude）的守则 · 专业桌面版 GUI

本目录是**设计**，不是代码。它告诉你界面要变成什么样；仓库根目录的 [AGENTS.md](../../../AGENTS.md) 和 [GUIDELINES.zh-CN.md](../../GUIDELINES.zh-CN.md) 告诉你怎么工作。两者冲突时，以 GUIDELINES 为准，并在 PR 里指出冲突。

## 先读

1. [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §0（定位、原则、与准则的差异）、§1（token）、§5（布局与断点）、§6（图表）。
2. [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md) §1（main 现状）、§2（已实现/未实现矩阵）、§11（逐文件计划）、§12（你要做的那个阶段）。
3. `screens/` 里与你的阶段对应的 PNG。

## 规则

- **一个阶段一个分支一个 PR**（P1…P4）。P0 是维护者的决定；P0 没确认的项（字体选项、D7 Lucide、准则差异）不要擅自实现，先问。
- **只改 `src/reverbscope/ui/`、打包配置、`tests/ui/`、`tests/unit/test_theme_tokens.py` 和本规格列出的文件。** 不改 `core/`、`display/`、`models/`、`io/`、`cli/`、`interpretation/` 的逻辑。图表只换“怎么画”，不换“画什么数”。
- **颜色、尺寸只从 token / `ui/layout.py` 来**，组件里不写十六进制、不写 `setStyleSheet`；状态用 Qt 伪状态和动态属性，QSS 只在 `theme.stylesheet()` 里生成。
- **现有 19 个 token 的值不改**；新键逐字照抄 DESIGN_SYSTEM §1.2。改了任何颜色，跑对比度测试，必须 0 失败。
- **不要实现设计稿里标“未实现”的东西，除非它属于你的阶段。** 也不要在产品界面里放“未实现”徽章——徽章只存在于设计稿。
- **pyqtgraph 只从 `ui/pg.py` 取**（`tests/unit/test_pg.py` 会查）。不开 OpenGL，不加 QtCharts/QtGraphs。
- **保持现有行为和测试**：Esc 停止、切换视图不中断测量、`view_chosen` 信号、`set_navigator_open()` / `set_inspector_open()`、Ctrl+1…9/0。需要改测试时只放宽到新规格（例如图表最小宽 320 → 640），并在 PR 说明。
- 新字符串走 `_()`，中文 `.po` 同步；按钮用动词，提示最多两行（准则 §16）。
- 数字：Plex Mono、U+2212 负号、数值与单位间一个空格、不可靠写 `(x.xx)?`。

## 完成的定义（每个阶段）

- 本规格 §12 该阶段的验收条目逐条打勾，写在 PR 描述里。
- 离屏截图：1440×900、1100×720、960×640 × 浅/深 × 中/英，附在 PR 里，并与 `screens/` 对照说明差异。
- `pytest`（含 `tests/ui`，离屏）全绿；ruff / mypy 按仓库配置通过。

## 重新生成设计稿

`prototype/` 是出图用的 PySide6 + pyqtgraph 脚本（不是产品代码，不要从这里复制组件）。需要：

```
pip install "PySide6_Essentials>=6.11,<6.12" pyqtgraph==0.14.0 numpy soundfile
reverbscope demo --out /tmp/rs-demo               # 合成演示数据（同一版本的 main）
# Lucide SVG（lucide-static 0.460.0，ISC）放进一个目录；字体（OFL 1.1）放进另一个目录：
#   IBMPlexSans-{Regular,Medium,SemiBold}.ttf  IBMPlexMono-{Regular,Medium,SemiBold}.ttf
#   SourceHanSansCN-{Regular,Medium,Bold}.otf
cd docs/design/pro/prototype
RS_ICONS=/path/lucide RS_FONT_DIR=/path/fonts RS_DEMO_DIR=/tmp/rs-demo RS_OUT=/tmp/pro-screens \
QT_QPA_PLATFORM=offscreen python render_pro.py
python contrast_pro.py --md /tmp/CONTRAST.md
```

`render_pro.py` 会打印可能被截断的文字（`CLIPPED:`）；每张图都要人工看一遍。
