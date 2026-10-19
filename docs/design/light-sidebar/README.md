# 浅色侧栏设计基线（light-sidebar baseline）

**状态：提案 · 设计稿 · 待维护者决定。** 本目录提出把 2026-10-18 首次启动原型的浅色“侧栏”风格作为 ReverbScope GUI 的设计基线，**取代 PR #71 的深色 Photoshop 式方向作为设计目标**。PR #71 的分步测量流程、全部分析视图、对比、房间、项目/设置功能都保留；PR #87 的评审要求和 PR #89 验收发现的问题（BUSY / ESC / SAFE / FLOW / 布局）都写进了规格与验收标准。
维护者的追加要求已纳入：“布局好看点”（SPEC §1 列出 10 项布局精修）和“借鉴苹果的设计，功能图标与 GUI 完美贴合”（合一工具栏、vibrancy 侧栏、原生感控件；统一 Lucide 图标家族与图标→功能表，SPEC §16）。

> 只有文档和设计稿：不改 `src/`、DSP、CLI、数据模型、测试、AGENTS.md、GUIDELINES；不碰其他分支；不合并任何 PR。设计稿是离屏绘制的**静态 mockup，不是交互验证**；数据来自 `reverbscope demo`（合成演示）。代码里还没有的东西统一标 **未实现**。

## 文件

| 文件 | 内容 |
|---|---|
| [SPEC.md](SPEC.md) | 视觉规格：原则、布局精修、浅/深 token 与对比度、字体、间距、侧栏 / 工具栏 / 首页 composer / 测量步骤流 / 检查器 / 图表 / 对比 / 设置、断点、快捷键与 Esc 顺序、用户类型契约、图标规格与许可证、待决定事项 |
| [MAPPING.md](MAPPING.md) | PR #71 元素 → 新基线元素：保留 / 改 / 新增 / 删除 / 未实现 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 实现后的验收标准（VIS / ICON / LAY / BUSY / ESC / SAFE / FLOW / CHART / MODE） |
| [HANDOFF.md](HANDOFF.md) | 给实现者：建议拆分的 PR、代码落点、实现提示、如何重新生成设计稿 |
| `mockups/` | 20 张高保真设计稿（zh 浅色为主，关键屏另有 en 浅色与 zh 深色；含 960×640 与 1440×900） |
| `icons/` | 用到的 42 个 Lucide 图标（lucide-static 1.59.0，ISC）+ 许可证全文 |
| `source/` | 设计稿渲染器（PySide6 QPainter，离屏）、对比度脚本、演示数据缓存 `demo.npz` |

## 关键设计稿

| | |
|---|---|
| 首页 / 空状态 | `mockups/01-home.zh-light.1280.png` |
| 步骤 2 · SAFE（−9 dBFS 未确认，继续禁用 + 原因） | `mockups/03-measure-2-safe.zh-light.1280.png` |
| 步骤 3 · 测量中（锁定 + 唯一 Stop） | `mockups/04-measure-3-running.zh-light.1280.png` |
| 频响 + 基线差值 | `mockups/05-analysis-fr.zh-light.1280.png` |
| 衰变 / 瀑布 / 对比 / 设置 | `mockups/06…09-*.png` |
| 960×640 | `mockups/10-narrow-fr.zh-light.960.png`、`mockups/10b-narrow-measure-safe.zh-light.960.png` |
| 图标规格 | `mockups/11-icon-spec.zh-light.1280.png` |

## 参考来源

- 10-18 首次启动 / 设置 / 关于原型（16、16b、10、10c、04、15c 等，浅色侧栏 260、teal 强调色、keycap 提示、composer、三种用户类型）。
- PR #71 `e39185c`（分步测量、分析视图）、PR #87 REVIEW/SPEC（P0：SAFE / FLOW / BUSY / ESC，图表视觉）、PR #89 `1ea78b3` 验收报告（剩余 P0/P1）。
- 代码基线：main `ab3da19`。
