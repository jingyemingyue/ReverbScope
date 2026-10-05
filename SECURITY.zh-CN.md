# 安全策略

[English](SECURITY.md) | **简体中文**

本文是 [SECURITY.md](SECURITY.md) 的简体中文翻译；两者不一致时以英文版为准。

## 受支持的版本

RoomScope 目前是预发布版本（0.4.x，见 [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md)，中文摘要见 [docs/RELEASE_PLAN.zh-CN.md](docs/RELEASE_PLAN.zh-CN.md)）。只维护 `main` 分支和最新的 0.4.x 版本。仓库是公开的；发布版本都是 GitHub Releases 上的预发布版本，PyPI 上没有任何发布。

## 报告漏洞

请使用本仓库的 GitHub 私密漏洞报告功能（**Security → Report a vulnerability**）。可能被滥用的问题，请不要用公开 issue 报告。

如果私密报告功能尚未开启，请通过 GitHub 联系仓库所有者。通常几天内会得到回复。报告可以用中文书写。

## 哪些不属于安全问题

RT60 数值错误、出乎意料的有效性标记、界面布局缺陷，以及类似的分析或易用性问题，都是普通缺陷。请提交[测量问题](https://github.com/jingyemingyue/RoomScope/issues/new?template=measurement-zh-CN.yml)或[缺陷报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug-zh-CN.yml) issue（英文表单：[measurement](.github/ISSUE_TEMPLATE/measurement.yml)、[bug](.github/ISSUE_TEMPLATE/bug.yml)），并附上 [CONTRIBUTING.md](CONTRIBUTING.md) 中列出的文件。

## 来自他人的文件

会话文件夹、打包文件、`comparison.json`、`project.json`、扫频配套文件和 WAV 文件都被当作不可信数据处理。RoomScope 从不对它们做反序列化（unpickle）或求值，限制 JSON 的大小和嵌套深度，其设计目标是把格式错误的内容变成 `RoomScopeError` 而不是崩溃（`tests/robustness/`），并且只在会话自身的文件夹内读取该会话的 `result.json` 和 `impulse_response.wav`（`session.json` 中的绝对路径或指向文件夹之外的路径会被拒绝）。把打开的会话另存到其他文件夹时，只会从该会话自身的文件夹内复制扫频配套文件和录音。`roomscope session bundle` 会略去任何链接到会话文件夹之外的文件，因此别人的会话无法把你的某个文件塞进你附到公开 issue 上的 zip 中。`project.json` 在设计上有所不同：它列出的会话文件夹可以位于任何位置，所以打开别人的项目就会打开其中指名的会话文件夹——请先查看它的内容。除此之外，任何能让 RoomScope 读写你所打开的文件之外内容的方法，都属于安全问题。

## 独立模式的安全性

RoomScope 会通过扬声器播放测试扫频。默认值保持保守（独立模式为 −20 dBFS；生成的扫频文件为 −12 dBFS）。默认情况下，本项目不会更改系统音量、音频设备配置或 DAW 设置。唯一需要主动开启的例外是 `roomscope measure --coreaudio-set-rate`（开发者版独立模式中对应的复选框）：它允许 PortAudio 在本次测量中设置所选 macOS 设备的标称采样率，这可能干扰正在使用该设备的其他程序。测量结束后是否会恢复原来的采样率尚未检查；可在“音频 MIDI 设置”中查看设备的采样率。如发现任何其他更改，请作为安全问题报告。
