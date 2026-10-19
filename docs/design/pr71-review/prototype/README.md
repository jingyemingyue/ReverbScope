# 设计稿渲染器（只用于文档，不是产品代码）

`v2screens.py` 在 PR #79（`design/pro-desktop-system`，`docs/design/pro/prototype/`）的原型套件
（`pk.py`、`pshell.py`、`pscreens.py`、`charts.py`、`pdata.py`）之上，替换应用栏、底部栏与 token，
并新增测量向导的两个画面。本目录**不复制** PR #79 的套件；渲染时把它放进 `PYTHONPATH`。

```bash
# 1. PR #79 的套件、Lucide 图标、字体和 demo 数据（路径按本机调整）
export PYTHONPATH=/path/to/design-pro-desktop-system/docs/design/pro/prototype:$PWD
export RS_MAIN=/path/to/ReverbScope/src
export RS_ICONS=/path/to/lucide-static-0.460.0/icons
export RS_FONT_DIR=/path/to/fonts          # IBM Plex Sans/Mono + Source Han Sans CN（OFL）
export RS_DEMO_DIR=/path/to/demo           # `reverbscope demo --out DIR` 的输出
export RS_OUT=/tmp/pr71-v2
QT_QPA_PLATFORM=offscreen python render_v2.py          # 10 张设计稿
python compose.py                                      # 前后对照（需先渲染 BEFORE）
python contrast_pr71_baseline.py                       # PR #71 现状对比度
```

BEFORE 图由仓库脚本在 `e39185c` 上渲染：

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python scripts/render_gui2_screenshots.py \
  --out /tmp/pr71-before --lang zh_CN --width 1280 --scheme dark \
  --view measure_signal --view measure_review --view fr --view decay --view waterfall
```

渲染器会检查文字 / 按钮截断并打印 `CLIPPED`；提交的 10 张设计稿渲染时无截断报告。
