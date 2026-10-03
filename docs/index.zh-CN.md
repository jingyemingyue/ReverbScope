# RoomScope 文档索引

[English](index.md) | **简体中文**

RoomScope 用来测量录音房间，让你听清房间对近距离拾音的声源做了什么。本页是仓库里已有的文档站：安装、扫频流程、跟随 DAW、以及分析报告。

RoomScope 目前是预发布版本：还没有任何结果在真实硬件上测量并与参考仪器对照过，安装包没有用于分发的签名，通用 DAW 模式的各 DAW 步骤是按厂商文档编写、尚未在 DAW 中实测的流程。RoomScope 不给房间打分。

HTML 文档站由 `python scripts/build_docs_site.py --out site` 从本目录生成（每页标题与摘要、规范网址、Open Graph、`sitemap.xml`、`robots.txt`）。仓库还没有公开的文档主机；规范网址使用占位符 `https://docs.example.invalid/roomscope/`，可用 `--base-url` 替换。把 `site/` 拷到静态主机即可。本仓库不会向 Google 提交站点、也不会购买域名或开通主机账号。

用户文档提供英文和简体中文两种版本，**以英文版为准**；每篇中文文档顶部都有指向英文原文的链接。开发者与内部文档（架构、ADR、研究笔记、依赖与许可证审查、代码来源、项目状态、发布计划）只提供英文版，其中发布计划和 v1.0 架构另有中文摘要。

## 中文用户文档

- [项目简介（README.zh-CN.md）](https://github.com/jingyemingyue/RoomScope/blob/main/README.zh-CN.md)
- **[下载与安装](INSTALLATION.zh-CN.md)**：macOS、Windows、Linux 和 Python 的安装、更新、卸载、未签名构建的警告与故障排查
- [用户指南](user-guide/zh-CN.md)：安装、通用 DAW 模式、独立模式、读懂结果、故障排查、报告问题
- [用 DAW 测量](user-guide/daw-setup.zh-CN.md)：Pro Tools、Logic Pro / GarageBand、Cubase / Nuendo、Fender Studio Pro、Ableton Live、REAPER、FL Studio、Bitwig Studio、Digital Performer、Audacity 及其他 DAW
- [兼容性](COMPATIBILITY.zh-CN.md)：支持的系统和文件格式，以及每一项的验证方式
- [桌面版、终端版与开发者工具](EDITIONS.zh-CN.md)
- [与同类工具的比较](COMPARISON.zh-CN.md)
- [音频设备与主机 API](AUDIO_DEVICES.zh-CN.md)
- [硬件测试矩阵](HARDWARE_TESTS.zh-CN.md)：如何用你的音频接口或 DAW 帮忙测试
- [安全策略](https://github.com/jingyemingyue/RoomScope/blob/main/SECURITY.zh-CN.md)

## 中文问题表单

- [音频接口测试报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware-zh-CN.yml)
- [DAW 兼容性报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw-zh-CN.yml)
- [测量问题](https://github.com/jingyemingyue/RoomScope/issues/new?template=measurement-zh-CN.yml)
- [缺陷报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug-zh-CN.yml)

## 中文摘要（开发者文档）

- [发布计划（中文摘要）](RELEASE_PLAN.zh-CN.md)
- [v1.0 架构设计（中文摘要）](ARCHITECTURE_V1.zh-CN.md)
- [项目需求书（原文存档）](PROJECT_BRIEF.zh-CN.md)

## 仅有英文版的文档

- [验证方案](VALIDATION.md)（VALIDATION.md）
- [测量方法](MEASUREMENT_METHODOLOGY.md)（MEASUREMENT_METHODOLOGY.md）
- [贡献指南](https://github.com/jingyemingyue/RoomScope/blob/main/CONTRIBUTING.md)（欢迎在 issue 中使用中文）
- [更新日志](https://github.com/jingyemingyue/RoomScope/blob/main/CHANGELOG.md)
- 其余开发者文档见[英文文档索引](index.md)。
