# Phase 0：设置页只显示当前语言

对应 GUI 执行准则 §7.14、§11.4 第 3 项、§15 Phase 0、§5 C10/C12。
重启提示现在通过已登记词条显示当前语言，选择新语言仍只影响下一次启动。
原有“选择语言不切换当前窗口”断言保留；移除中文门对这句英文的旧豁免，
只保留设备名和语言自称的正当数据豁免。没有数值、CLI、设置格式或依赖变化。

## 验证

- 修复前，两种语言的新增精确文案断言及收紧后的中文门共 3 项失败。
- 修复后，全部 GUI 中文/词条检查 23 项通过。
- 完整离屏 suite：3445 passed、2 既有平台 skipped，core/models 分支覆盖率
  93.43%，通过 85% 门。Ruff、format、严格 mypy（有 Qt 与无 Qt/Linux）、
  文档/CLI/源码安全检查通过。
- Windows 的既有窄窗口失败仍是另一项基线缺陷，由独立布局任务处理；本修复
  未改变测量条。新 head CI、原生/真实音频/旁白/打包交互和独立复评待完成。
- 文档站的五张旧图固定链接与 Phase 0 基线任务相同，保留同一前置修复。

## 合成离屏对照

前为 #58 `2560124`，后为代码提交 `4793654`；图像归档 `d554255`。
960×640/1280×800 是父窗口请求尺寸，设置对话框保持其自然大小；不能把
文件名当作对话框实际尺寸或原生验收。

| 语言/主题/父窗口 | 前 | 后 |
| --- | --- | --- |
| zh_CN / light / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/zh_CN-light-1x-960x640-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/zh_CN-light-1x-960x640-settings.png) |
| zh_CN / light / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/zh_CN-light-1x-1280x800-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/zh_CN-light-1x-1280x800-settings.png) |
| zh_CN / dark / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/zh_CN-dark-1x-960x640-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/zh_CN-dark-1x-960x640-settings.png) |
| zh_CN / dark / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/zh_CN-dark-1x-1280x800-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/zh_CN-dark-1x-1280x800-settings.png) |
| en / light / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/en-light-1x-960x640-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/en-light-1x-960x640-settings.png) |
| en / light / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/en-light-1x-1280x800-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/en-light-1x-1280x800-settings.png) |
| en / dark / 960×640 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/en-dark-1x-960x640-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/en-dark-1x-960x640-settings.png) |
| en / dark / 1280×800 | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/before/en-dark-1x-1280x800-settings.png) | [合成离屏图](https://github.com/jingyemingyue/ReverbScope/blob/d5542553a720b79d5e2f46258ce17761bcb4457c/docs/images/gui-redesign/p0-settings/after/en-dark-1x-1280x800-settings.png) |
