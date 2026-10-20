[English](SUPPORT.md) | **简体中文**

# 获取帮助与反馈

ReverbScope 是在 GitHub 上维护的预发布软件。提问、缺陷报告和测试结果都通过
[issue 表单](https://github.com/jingyemingyue/ReverbScope/issues/new/choose)提交；每个表单都有英文和简体中文两个版本。
目前没有邮件列表、聊天群或论坛。

| 你想要 | 使用 |
| --- | --- |
| 询问某个功能怎么用，或提出一般性反馈 | [提问或反馈](https://github.com/jingyemingyue/ReverbScope/issues/new?template=feedback-zh-CN.yml) |
| 报告崩溃、报错或不正确的行为 | [缺陷报告](https://github.com/jingyemingyue/ReverbScope/issues/new?template=bug-zh-CN.yml) |
| 报告看起来不对的数值或有效性标记 | [测量问题](https://github.com/jingyemingyue/ReverbScope/issues/new?template=measurement-zh-CN.yml) |
| 建议一项改动 | [功能请求](https://github.com/jingyemingyue/ReverbScope/issues/new?template=feature-zh-CN.yml) |
| 报告在真实音频接口上的运行结果 | [音频接口测试报告](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware-zh-CN.yml) |
| 报告通过 DAW 的运行结果 | [DAW 兼容性报告](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw-zh-CN.yml) |
| 报告安全问题 | 按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md) 私下报告，不要提交公开 issue |

## 从桌面应用反馈

**帮助 → 发送反馈…** 和 **帮助 → 报告问题…** 会在浏览器里打开对应的表单，语言跟随界面语言，
并且已经填好 ReverbScope、Python、Qt 的版本和操作系统。应用本身不发送任何内容：所有字段都在浏览器里
给你看，由你决定是否提交。

## 有帮助的信息

* 环境报告：在应用里选 **帮助 → 用于问题报告的环境报告 → 复制**，或在终端运行 `reverbscope doctor`
  （涉及音频设备时加 `--probe`）。设备名称里可能含有个人姓名，发布前请检查一遍。
* 如果是测量问题，在可以分享的情况下附上会话文件夹或你分析的文件。
* 结果来自真实音频接口、DAW、合成演示，还是 fake 后端。只有在实体音频接口上的运行才算硬件测试
  （[docs/HARDWARE_TESTS.zh-CN.md](docs/HARDWARE_TESTS.zh-CN.md)）。

提问之前，可以先看[用户指南](docs/user-guide/zh-CN.md)、[安装指南](docs/INSTALLATION.zh-CN.md)
及其中的故障排查一节，常见问题大多有答案。
