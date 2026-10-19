# PR #71 设计评审 v2

对 PR #71（`gui/photoshop-focused` @ `e39185c`）的设计评审与下一版设计稿。只含文档与设计稿，不改 `src/`。

| 文件 | 内容 |
| --- | --- |
| [REVIEW.md](REVIEW.md) | 评审报告：证据级别、SAFE-01 / BUSY-01 / FLOW-01 / ESC-01 状态、P0/P1/P2 问题表、DAW 交互对照、交互 QA 清单、前后对照图 |
| [SPEC.md](SPEC.md) | 视觉规格：网格、间距、字号、深浅色 token 与对比度、图表样式、组件状态、断点、快捷键与 Esc 优先级、准则差异 |
| [HANDOFF.md](HANDOFF.md) | 给 GUI 开发者的实施顺序，逐项对应 PR #71 的文件与部件，并标明“需代码 / 需 core / 维护者决定” |
| [CONTRAST.md](CONTRAST.md) | PR #71 现状与 v2 token 的 WCAG 对比度表 |
| `images/before/` | **PR #71 @ e39185c 实际离屏渲染**（仓库脚本，合成演示数据） |
| `images/after/` | **设计稿（design mockup），非交互验证** |
| `images/compare/` | 前后对照（左：实际渲染；右：设计稿） |
| `prototype/` | 设计稿渲染器与对比度脚本（只用于文档） |
| [evidence/renders.json](evidence/renders.json) | 每张图的来源、尺寸与 SHA-256 |

静态截图不是交互验收；见 [REVIEW.md §6](REVIEW.md)。
