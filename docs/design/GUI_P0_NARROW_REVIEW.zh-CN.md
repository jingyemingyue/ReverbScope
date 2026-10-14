# Phase 0：测量条动态宽度修复记录

对应执行准则 §5 C8/C12、§13.4、§15 Phase 0、§16。
本任务只修复基线已有的自适应布局；不启动 Phase 2 测量条重写。

## 问题与行为证据

#58 的 CI #204 中，Windows 英文窄窗口测试报告最小宽度提示 986 > 960。
本机另行重现了控件内容/尺寸提示变化而窗口不变时，测量条保留旧单行布局，
让设置区挤占运输按钮的问题；新增回归测试先失败。

Qt 的 `minimumSizeHint()` 可能保持旧最小值，而 `sizeHint()` 已按新内容增长。
修复用首选宽度判断分行，并在布局请求时重新判断；方向未改变时不再触发布局。
没有轮询、驻留辅助进程、新颜色/尺寸字面量、依赖或可见字符串。

现有 960×640 中英文可读性、1920 单行、设备双向镜像、视图切换和 Stop/Esc
断言全部保留。新增测试证明：不调整窗口大小也会分行，停止/开始/阶段文字
保持可见且不与设置区重叠；文字恢复后会恢复单行。

## 已运行与待验证

- Apple Silicon / Python 3.12.14 / PySide6 Essentials 6.11.2：本文件相关 17 项通过。
- 全部 GUI 加文档站：166 项通过；中文门、生命周期和未保存保护均在其中。
- Ruff、format、严格 mypy（含 Qt 和 CI 的无 Qt/Linux 语义）、文档/CLI/源码安全：通过。
- README 图像已用既有脚本从合成数据重新生成；以下前后对照均为离屏。
- 完整离屏 suite：3444 passed、2 既有平台 skipped；core/models 分支覆盖率
  93.43%，85% 门通过。文档站的 9 项检查在加入此记录后再次通过。
- 新 head Windows CI：尚未运行，不能把本机可复現修复当作 Windows 通过。
- macOS 原生、Windows 真机、真实声卡/DAW、旁白、打包应用：未运行。

## 前后对照

前：#58 `2560124`；后：代码修复提交 `581fdff`。PNG 均附合成/离屏标记和
源代码提交。图像归档提交为 `0230a3e`，链接固定在该提交，避免历史证据漂移。

| 语言/主题/父窗口尺寸 | 前 | 后 |
| --- | --- | --- |
| zh_CN / light / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/zh_CN-light-1x-960x640-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/zh_CN-light-1x-960x640-standalone.png) |
| zh_CN / light / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/zh_CN-light-1x-1280x800-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/zh_CN-light-1x-1280x800-standalone.png) |
| zh_CN / dark / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/zh_CN-dark-1x-960x640-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/zh_CN-dark-1x-960x640-standalone.png) |
| zh_CN / dark / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/zh_CN-dark-1x-1280x800-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/zh_CN-dark-1x-1280x800-standalone.png) |
| en / light / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/en-light-1x-960x640-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/en-light-1x-960x640-standalone.png) |
| en / light / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/en-light-1x-1280x800-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/en-light-1x-1280x800-standalone.png) |
| en / dark / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/en-dark-1x-960x640-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/en-dark-1x-960x640-standalone.png) |
| en / dark / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/before/en-dark-1x-1280x800-standalone.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/0230a3e236e746a5d93a9d420190ec491fff9eaa/docs/images/gui-redesign/p0-narrow/after/en-dark-1x-1280x800-standalone.png) |

## 评审范围

本修复沿用基线旧组件，未新增组件；Phase 1 的设计 token、组件画廊与整体
无障碍/样式迁移仍待实施。本次没有为旧界面整体宣称 §16.2 的 20/24 通过。
既有长表单、菜单助记符等问题仍按原阶段处理，不能由这项布局补丁代替。
复评需核对本次受影响控件的可读性、无重叠和停止入口，以及新 head 的 Windows
结果；独立复评尚待维护者或另一个会话完成。

五张旧验收图片的文档站链接修复与 Phase 0 基线任务相同，是 #58 已知 CI
前置缺陷；本分支一并保留相同固定链接，以便自己的文档门独立通过。
