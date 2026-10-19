# 浅色侧栏基线 · 交接说明（给实现者）

本 PR 只有文档和设计稿。实现要等维护者对 SPEC §19 的决定（至少 D-1 方向、D-2 字体、D-3 图标、D-4 视图分组）。下面是建议的实现顺序和代码落点，供后续 PR 使用；**本 PR 没有改任何代码**。

## 1. 起点

- 代码基线建议：先让 PR #89 的 P0 修完并合入 #71（CI-01、ESC-R1、BUSY-02），再在 #71 上换皮。分步结构、门控、Stop 固定这些行为已在 #71/#89 里，不要重写。
- 设计稿是视觉目标，不是像素级规格；以 SPEC 的 token 和尺寸为准。

## 2. 建议拆成的 PR

| 顺序 | 内容 | 主要文件（PR #71 路径） | 验收 |
|---|---|---|---|
| 1 | Token 换表：新增 SPEC §2 的 token 名（浅/深），旧名做别名过渡 | `ui/design/tokens.py`、`ui/design/styles.py`、`ui/theme.py` | VIS-01/02 |
| 2 | 外框：侧栏 260 + 合一工具栏 52；删除上下文栏、竖向指针工具栏、任务按钮 | `main_window.py`、`navigator.py`、`ui/components/context_bar.py`、`analysis_workspace.py` | LAY-03/04 |
| 3 | 测量流程换皮：步骤条组件、表单列 600 + 就绪栏 280、操作栏 64 对齐表单列、SAFE 色带 | `pages.py`、`measure_strip.py` | FLOW-*、SAFE-*、LAY-05 |
| 4 | BUSY/ESC 补齐：保存锁定、菜单原因、Esc 第 3 级（模态/他窗放行）、停止后关弹层 | `main_window.py`（`_busy_locked_actions`、`handle_escape`） | BUSY-*、ESC-* |
| 5 | 图表浅色 plot token + 角色线型 + 读数栏 + 评估带/拟合线/截断 | `plotkit.py`、`views/frequency.py`、`views/decay.py`、`views/timefreq.py` | CHART-* |
| 6 | 检查器 288 + 三段；对比模式页 | `inspector.py`、`compare_view.py` | — |
| 7 | 首页 composer、设置窗口、用户类型 | `start_panel.py`、`settings_dialog.py` | MODE-* |
| 8 | 图标：Lucide SVG 子集 + 统一加载器（按尺寸换算线宽 1.5 px、按状态着色） | 新 `ui/icons/`；第三方许可证窗口 | ICON-* |

## 3. 实现提示

- **线宽换算**：Lucide viewBox 为 24；渲染 16 px 时把 `stroke-width` 设为 `1.5*24/16 = 2.25`，18 px → 2.0，20 px → 1.8，14 px → 2.57（或 1.25 px → 2.14）。设计稿渲染器 `source/lk.py` 的 `Canvas.icon()` 就是这么做的。
- **vibrancy**：macOS 用原生 `NSVisualEffectView`（通过 `winId()` + PyObjC 或 Qt 的 `QMacNativeWidget` 方案），失败时回退渐变；Windows/Linux 直接用渐变。
- **Esc**：应用级过滤器里先判断是否发声（停止并 `activePopupWidget().close()`），再判断 `QApplication.activeModalWidget()` 或事件目标 `window() is not self` → 返回 False 交给对话框。
- **SAFE**：把“清除确认”收敛成一个函数，挂到电平 `valueChanged`、`_go_home/show_home`、停止、完成、失败五处。
- **Stop 唯一**：用同一个 `QAction`，测量页时放操作栏，否则放工具栏；两处不同时可见。
- **960 高度测试**：不要依赖干净的 ui.ini；测试前显式重置抽屉/工具栏状态或在布局里给图表设最小伸缩比。

## 4. 不要做

- 不改 DSP、CLI、数据模型、阈值、有效性判定。
- 不打包 SF Symbols。
- 不把演示数据标签去掉。
- 不在本基线落地前修改 GUIDELINES 或 AGENTS.md（需要维护者另行决定）。

## 5. 重新生成设计稿

```
cd docs/design/light-sidebar/source
python prep.py              # 可选：从 `reverbscope demo` 输出重算 demo.npz（需要 RS_DEMO_DIR、PySide6、soundfile）
QT_QPA_PLATFORM=offscreen RS_FONT_DIR=/path/to/fonts RS_DEMO_DIR=/path/to/demo python render.py
python contrast.py          # 重算对比度表
```

字体文件未入库：IBM Plex Sans/Mono、Source Han Sans CN、Source Serif 4、LXGW WenKai（均 OFL-1.1）。`RS_DEMO_DIR` 指向 `reverbscope demo` 生成的目录（含 `position-a/`、`position-b/`、`comparison.json`）。渲染器会报告任何文字溢出（本次 0 处）。
