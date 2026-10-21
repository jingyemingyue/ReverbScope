# 公开 beta：下载、校验、体验

[English](PUBLIC_TESTING.md) | **简体中文**

**2026-10-21 核对：** [GitHub Releases](https://github.com/jingyemingyue/ReverbScope/releases)
中最新的公开预发布版是 **[v0.5.0b6](https://github.com/jingyemingyue/ReverbScope/releases/tag/v0.5.0b6)**（beta 6），
2026-10-21 发布，是第一个使用 **ReverbScope** 名称的公开构建。更早的 v0.5.0b1 和 v0.4.1 预发布版
仍然公开，沿用旧名 RoomScope。b2–b5、rc1、rc2 都是 Draft，访客无法下载。没有稳定版。
以后版本请重新核对 Releases，不要把这份带日期的说明当作实时状态。

## 1. 下载一个版本

在 v0.5.0b6 展开 **Assets**；安装包不需要 Python 或 Git。

| 电脑 | 桌面版：GUI 和命令行 | 终端版：只有命令行 |
| --- | --- | --- |
| Apple 芯片，macOS 14+ | `ReverbScope-Desktop-macOS-arm64.dmg` | `ReverbScope-Terminal-macOS-arm64.tar.gz` |
| Intel Mac，macOS 14+ | `ReverbScope-Desktop-macOS-x86_64.dmg` | `ReverbScope-Terminal-macOS-x86_64.tar.gz` |
| Windows 10/11 x64 | `ReverbScope-Desktop-Windows-x64-Setup.exe` 或 `ReverbScope-Desktop-Windows-x64.zip` | `ReverbScope-Terminal-Windows-x64.zip` |
| Linux x86_64，glibc 2.39+ | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | `ReverbScope-Terminal-Linux-x86_64.tar.gz` |

这些是构建目标，不等于已验证的声卡/驱动组合。同一发布中还需下载 `SHA256SUMS`。
`cyclonedx.sbom.json` 和 `generated-bundle.lock` 说明该包的依赖；不能拿当前源码的锁文件或
Draft 的校验值代替公开包的文件。

## 2. 打开前核对 SHA256

将所选文件的完整哈希与同版 `SHA256SUMS` 中对应行逐字对照：

```bash
shasum -a 256 ReverbScope-Desktop-macOS-arm64.dmg
sha256sum ReverbScope-Desktop-Linux-x86_64.tar.gz
```

Windows PowerShell：

```powershell
Get-FileHash .\ReverbScope-Desktop-Windows-x64-Setup.exe -Algorithm SHA256
```

不一致就停止，重新下载，并报告发布 URL 与文件名。校验和只能核对文件完整性，不代表签名或公证。

## 3. 安装并运行无声演示

- **Mac 桌面版：** 打开 DMG，把 **ReverbScope** 拖到应用程序，推出 DMG，再从应用程序启动。
  未签名提示出现后，在系统设置 → 隐私与安全性 → 仍要打开中处理；无需关闭 Gatekeeper 或 SIP。
  以后真实录音时允许麦克风权限。此应用**未经 Apple 公证**。
- **Windows 桌面版：** 运行 Setup 后从开始菜单打开 ReverbScope，或完整解压 ZIP 后启动
  `reverbscope-gui.exe`。SmartScreen 可能显示“更多信息 → 仍要运行”；若系统策略禁止，报告阻拦，
  不要关闭策略。这些包没有 Authenticode 签名。
- **Linux 桌面版：** 完整解压，安装[该版本安装文档](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b6/docs/INSTALLATION.zh-CN.md)
  列出的 PortAudio 与 Qt 系统库，再运行 `./reverbscope/reverbscope-gui`；中文图表需要 CJK 字体。
- **终端版：** 完整解压。Mac/Linux 运行 `./reverbscope-terminal/reverbscope demo`；Windows 打开
  **ReverbScope Terminal.cmd**，输入 `reverbscope.exe demo`。macOS 拒绝运行浏览器下载的未签名终端程序时，
  按[该版本安装文档](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b6/docs/INSTALLATION.zh-CN.md)的终端版一节处理。

桌面窗口没有演示按钮。先在命令行运行一次 `demo`：它为两个模拟位置写出 **Synthetic / Demo 合成演示**
会话，不播放声音。再在侧栏选 **打开会话…**，选演示文件夹里的 `position-a`。
这只展示软件流程，不测试声卡、房间或 DAW。安装包不会把命令加入 PATH；Mac 桌面版的命令示例：

```bash
/Applications/ReverbScope.app/Contents/MacOS/ReverbScope demo
```

Python 3.12+ 用户从同一发布下载 `reverbscope-0.5.0b6-py3-none-any.whl` 和 `generated-bundle.lock`，
新建独立虚拟环境后，将该发布的运行时版本与本地 wheel 一起安装。
不加约束的 GUI 依赖可能装上本 beta 未测试过的新 Qt：

```bash
python -m pip install -r generated-bundle.lock "./reverbscope-0.5.0b6-py3-none-any.whl[gui]"
reverbscope --help
reverbscope demo
```

没有 PyPI 版本：`pip install reverbscope` 装不到本项目。本 beta 的文档见
[固定到该标签的版本](https://github.com/jingyemingyue/ReverbScope/tree/v0.5.0b6/docs)。
beta 1 用的是 **RoomScope / `roomscope`** 名称，那些文件仍按它自己的
[标签文档](https://github.com/jingyemingyue/ReverbScope/tree/v0.5.0b1/docs)使用。

## 4. 反馈结果

按[社区测试指南](COMMUNITY_TESTING.zh-CN.md)操作，写明文件、SHA256、版本与构建。
失败和 NOT RUN 都有价值。真实播放前调低监听音量并确认路由。
目前没有真实声卡或 DAW 的 PASS 记录。若维护者分享准确的 Draft 构建，可以测试，
但报告中不能把它写成公开版。
