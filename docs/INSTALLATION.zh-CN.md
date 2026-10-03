# 安装 RoomScope

[English](INSTALLATION.md) | **简体中文**

> 本文是 [INSTALLATION.md](INSTALLATION.md) 的简体中文版本；两者不一致时，以英文版为准。

**下载页面（稳定 beta）：** <https://github.com/jingyemingyue/RoomScope/releases>

RoomScope 提供**两条 beta**。两条都还是 beta，都不是硬件验证版本。

* **稳定 beta** — 更少缺陷、功能面更窄。该页上最近一次已发布的预发布（`0.5.0b1`）。除非有人请你试预览，否则用这一条。
* **预览 beta** — 功能更强，可能不稳定。本 pull request（跟随 DAW、导入扫描、脉冲响应频谱、文档站 SEO）留在预览线路。**没有发布预览版 GitHub Release。**

打开下载页面，选最上方的最新**稳定**预发布，展开 **Assets**，只下载适合你电脑的那一个文件。RoomScope 有两个版本，
都不需要 Python 或 Git：

* **桌面版（Desktop Edition）**——带窗口和图表的应用程序，同时包含命令行。适合大多数人。
* **终端版（Terminal Edition）**——只有命令行，构建时不含图形界面（没有 Qt），体积约为桌面版的一半。适合脚本、
  自动化、服务器和没有图形桌面的电脑。

RoomScope 0.4.x 是**供测试用的早期公开预发布版本**。这些构建**没有签名**（见
[未签名构建的警告](#未签名构建的警告)），而且**还没有任何测量在真实音频硬件上验证过**
（[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)）。

## 我该下载哪个文件？

**桌面版**（图形界面 + 命令行）：

| 你的电脑 | 文件 | 章节 |
| --- | --- | --- |
| Apple 芯片（M1 及更新）的 Mac，macOS 14 或更新 | `RoomScope-Desktop-macOS-arm64.dmg` | [macOS](#macos) |
| Intel 处理器的 Mac，macOS 14 或更新 | `RoomScope-Desktop-macOS-x86_64.dmg` | [macOS](#macos) |
| Windows 10 或 11，64 位 | `RoomScope-Desktop-Windows-x64-Setup.exe`（安装程序）或 `RoomScope-Desktop-Windows-x64.zip`（免安装） | [Windows](#windows) |
| Linux x86_64（glibc 2.39 或更新，例如 Ubuntu 24.04+） | `RoomScope-Desktop-Linux-x86_64.tar.gz` | [Linux](#linux) |

**终端版**（只有命令行）：

| 你的电脑 | 文件 | 章节 |
| --- | --- | --- |
| Apple 芯片的 Mac，macOS 14 或更新 | `RoomScope-Terminal-macOS-arm64.tar.gz` | [终端版](#终端版) |
| Intel 处理器的 Mac，macOS 14 或更新 | `RoomScope-Terminal-macOS-x86_64.tar.gz` | [终端版](#终端版) |
| Windows 10 或 11，64 位 | `RoomScope-Terminal-Windows-x64.zip` | [终端版](#终端版) |
| Linux x86_64（glibc 2.39 或更新） | `RoomScope-Terminal-Linux-x86_64.tar.gz` | [终端版](#终端版) |

**Python 开发者**（任何装有 Python 3.12–3.14 的系统）：`roomscope-<version>-py3-none-any.whl` 或
`roomscope-<version>.tar.gz`，见 [Python](#python-wheel-和源码包)。

发布页上的其他文件用于核对和审计：`SHA256SUMS`（所有下载文件的校验和，见[核对下载的文件](#核对下载的文件)）、
`cyclonedx.sbom.json`（软件物料清单）和 `generated-bundle.lock`（构建里各个库的确切版本）。

## 支持的系统

| 系统 | 状态 |
| --- | --- |
| macOS 14 Sonoma 或更新，Apple 芯片或 Intel | 支持。DMG 在 GitHub 的 macOS 26（Apple 芯片）和 macOS 15（Intel）运行器上构建、挂载、安装并启动过，终端版也在这两种运行器上构建并运行过。macOS 14 是内置 NumPy / SciPy 的最低要求，但还没有实际运行过。不支持 macOS 13 及更早版本。 |
| Windows 10 / 11，x64 | 支持。安装程序在 GitHub 的 Windows 运行器上构建、静默安装、启动并卸载过，终端版也在上面构建并运行过。还没有记录过在个人 Windows 电脑上的测试。未测试 ARM 版 Windows 和 32 位 Windows。 |
| Linux x86_64 | 支持 glibc 2.39 或更新版本。两个版本都在 GitHub 的 Ubuntu 运行器上构建并做过冒烟测试。 |
| Python | 3.12、3.13、3.14（CI 在 Ubuntu 上跑全部三个版本，在 macOS 和 Windows 上跑 3.12）。 |

每一行由什么验证，详见 [COMPATIBILITY.zh-CN.md](COMPATIBILITY.zh-CN.md)。

## macOS

本节是**桌面版**；只有命令行的下载见[终端版](#终端版)。

### 安装

1. 在[下载页面](https://github.com/jingyemingyue/RoomScope/releases)下载
   `RoomScope-Desktop-macOS-arm64.dmg`（Apple 芯片）或 `RoomScope-Desktop-macOS-x86_64.dmg`（Intel）。不确定？
   苹果菜单 → **关于本机**：显示 *芯片 Apple M…* 的是 Apple 芯片，显示 *处理器 Intel* 的是 Intel。
2. 在“下载”文件夹里双击 DMG。会打开一个窗口，里面有 **RoomScope** 和一个 **Applications** 快捷方式。
3. 把 **RoomScope** 拖到 **Applications** 上。
4. 推出磁盘映像（访达边栏里 *RoomScope* 旁边的 ⏏ 按钮）。
5. 打开“应用程序”文件夹，双击 **RoomScope**。第一次打开时 macOS 会警告，按
   [下一节](#macos-首次打开)操作。

请从“应用程序”文件夹启动 RoomScope，不要直接在磁盘映像里运行。

### macOS 首次打开

这个应用没有经过 Apple 公证，所以第一次打开会被拦下：

1. macOS 提示 *未打开“RoomScope”* / *Apple 无法验证“RoomScope”是否包含可能危害 Mac 安全或泄漏隐私的恶意软件*。
   点 **完成**（不要点“移到废纸篓”）。
2. 打开 **系统设置 → 隐私与安全性**，向下滚动到 **安全性** 部分，会看到 *已阻止使用“RoomScope”，因为它不是来自已识别的开发者*
   之类的提示。
3. 点 **仍要打开**，在弹出的对话框里再点一次 **仍要打开**，需要时输入登录密码。

之后 RoomScope 会打开，以后再打开就不会警告了。**仍要打开** 按钮只在第一次尝试打开后出现，大约保留一小时。
在 macOS 14 上也可以按住 Control 键点按“应用程序”里的 RoomScope，选择 **打开**；从 macOS 15 起，这个办法不再能
跳过检查（[Apple](https://developer.apple.com/news/?id=saqachfa)）。Apple 对这个对话框的说明：
[安全地打开 Mac 上的 App](https://support.apple.com/zh-cn/102445)。

**不需要关闭 Gatekeeper 或系统完整性保护（SIP），我们也建议不要这样做。** 打开 RoomScope 不需要任何终端命令。

### 麦克风权限

第一次用 **独立模式** 测量时，系统会询问 *“RoomScope”想访问麦克风*：点 **允许**。如果点了“不允许”，之后可以在
**系统设置 → 隐私与安全性 → 麦克风** 里打开。录音只保存在你的电脑上；RoomScope 没有任何联网代码。

### macOS 上的命令行（可选）

应用里的可执行文件同时也是命令行工具：

```bash
/Applications/RoomScope.app/Contents/MacOS/RoomScope --help
/Applications/RoomScope.app/Contents/MacOS/RoomScope doctor
```

## Windows

本节是**桌面版**；只有命令行的下载见[终端版](#终端版)。

### 安装程序（推荐）

1. 在[下载页面](https://github.com/jingyemingyue/RoomScope/releases)下载 `RoomScope-Desktop-Windows-x64-Setup.exe`。
2. 运行它。如果 SmartScreen 提示“Windows 已保护你的电脑”，点 **更多信息 → 仍要运行**
   （见[警告说明](#未签名构建的警告)）。
3. 如果安装程序询问为所有用户还是只为你安装，选 **只为我安装**（不需要管理员权限）。RoomScope 会被安装到
   `%LOCALAPPDATA%\Programs\RoomScope`。安装界面按 Windows 显示语言使用英文或简体中文；可以勾选
   *创建桌面快捷方式*。
4. 从 **开始菜单 → RoomScope** 启动（或者在最后一页保持勾选“运行 RoomScope”）。命令行工具也一并安装在
   安装文件夹里：`roomscope.exe`。

### ZIP（免安装）

1. 下载 `RoomScope-Desktop-Windows-x64.zip`。
2. 右键点它 → **全部解压缩…** → **提取**。不要不解压就在 ZIP 里直接运行：程序需要旁边的 `_internal` 文件夹。
3. 打开解压出来的 `RoomScope-Desktop-Windows-x64` 文件夹，里面有：

   ```text
   roomscope-gui.exe        桌面程序（双击这个）
   roomscope.exe            命令行工具
   _internal\               程序库（要和 .exe 放在一起）
   THIRD_PARTY_LICENSES\    内置组件的许可证
   ```

4. 双击 **`roomscope-gui.exe`**。SmartScreen 可能会警告：**更多信息 → 仍要运行**。

整个文件夹可以移动到任何地方（比如“文档”），只要 `_internal` 和 `.exe` 文件在一起。要用命令行工具，在该文件夹
打开终端，运行 `.\roomscope.exe --help`。

### Windows 上的麦克风权限

如果看不到输入设备，或者录音是静音的，检查 **设置 → 隐私和安全性 → 麦克风**：*麦克风访问权限* 和
*允许桌面应用访问你的麦克风* 都必须打开。

## Linux

**桌面版**（只有命令行的下载见[终端版](#终端版)）：

```bash
tar xzf RoomScope-Desktop-Linux-x86_64.tar.gz
roomscope/roomscope-gui          # 桌面程序
roomscope/roomscope --help       # 命令行工具
```

程序包使用系统自带的 PortAudio 和图形库。在 Debian / Ubuntu 上：

```bash
sudo apt install libportaudio2 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0
sudo apt install fonts-noto-cjk   # 仅在图表里显示中文时需要
```

源码里的 `packaging/linux/roomscope.desktop` 是一个可以按需修改的桌面入口文件。程序包需要 glibc 2.39 或更新
（Ubuntu 24.04、Debian 13、Fedora 40 或更新）。

## 终端版

不带图形界面的命令行：所有 `roomscope` 命令（`demo`、`sweep`、`analyze`、`measure`、`compare`、`devices`、
`doctor`、`project`、`session`、`export` 等），支持英文和中文，分析与桌面版完全相同。它构建时不包含 Qt、PySide6
和图表库，所以体积约为桌面版的一半；`roomscope gui` 只会告诉你哪个下载带图形界面。

**macOS**（Apple 芯片用 `RoomScope-Terminal-macOS-arm64.tar.gz`，Intel 用
`RoomScope-Terminal-macOS-x86_64.tar.gz`）和 **Linux**（`RoomScope-Terminal-Linux-x86_64.tar.gz`）：

```bash
tar xzf RoomScope-Terminal-macOS-arm64.tar.gz      # 或者你下载的那个文件
cd roomscope-terminal
./roomscope --lang zh_CN demo                       # 体验一下：合成数据，不播放任何声音
./roomscope --help
```

`_internal` 文件夹要和 `roomscope` 放在一起。想在任何位置直接输入 `roomscope`，把该文件夹加入 `PATH`
（例如在 `~/.zshrc` 或 `~/.bashrc` 中加入 `export PATH="$HOME/roomscope-terminal:$PATH"`）。

在 **macOS** 上，浏览器会给下载的文件加上标记，macOS 会拒绝运行带这个标记的未签名命令行程序
（*无法打开“roomscope”，因为无法验证开发者*）。在包含 `roomscope-terminal` 的文件夹里运行一次下面的命令，
清除这个文件夹上的标记：

```bash
xattr -dr com.apple.quarantine roomscope-terminal
```

它只改动这些文件，不会关闭 Gatekeeper，也不应该关闭 Gatekeeper。这是未签名预发布构建的临时办法；签名后的构建不需要这一步。用 `curl` 下载的文件没有这个标记。Linux 终端版
做测量时需要 `libportaudio2`（`sudo apt install libportaudio2`），不需要图形库。

**Windows**（`RoomScope-Terminal-Windows-x64.zip`）：右键 → **全部解压缩…**，打开解压出的文件夹，双击
**`RoomScope Terminal.cmd`**。它会在该文件夹里打开一个命令提示符，可以直接输入 `roomscope.exe demo` 或
`roomscope.exe --help`。（直接双击 `roomscope.exe` 的话，窗口会在输出后立刻关闭。）在 PowerShell 中，于该文件夹运行
`.\roomscope.exe demo` 也一样。

## Python wheel 和源码包

RoomScope **还没有发布到 PyPI**，所以 `pip install roomscope` 装不到本项目；在本页另有说明之前，PyPI 上名为
`roomscope` 的包都不是我们发布的。请使用发布页附带的文件，或者克隆仓库。

### 用发布页的 wheel 安装

需要 Python 3.12 或更新。下载 `roomscope-<version>-py3-none-any.whl`，然后：

```bash
python3 -m venv roomscope-env
source roomscope-env/bin/activate          # Windows：roomscope-env\Scripts\activate
pip install "./roomscope-0.5.0b1-py3-none-any.whl[gui]"
roomscope --help
roomscope gui                              # 或者：roomscope-gui
```

只需要命令行工具和 Python API 时，去掉 `[gui]`（不装 PySide6，安装后约 230 MB）；这时 `roomscope gui` 会告诉你
怎样补装。不接音频接口先试一次：

```bash
roomscope --backend fake measure --out demo/ --duration 2 --post-silence 1.5
roomscope show demo/
```

`roomscope-<version>.tar.gz` 是源码包：`pip install "./roomscope-0.5.0b1.tar.gz[gui]"` 会在本地构建出同样的 wheel。

### 开发者安装（从 Git）

```bash
git clone https://github.com/jingyemingyue/RoomScope.git
cd RoomScope
python3.12 -m venv .venv
source .venv/bin/activate                  # Windows：.venv\Scripts\activate
pip install -e ".[dev,gui]"
roomscope --help
pytest
```

贡献者要跑的检查见 [CONTRIBUTING.md](../CONTRIBUTING.md)。开发者安装会显示桌面构建里隐藏的音频设备检查器和高级
音频流选项（[EDITIONS.zh-CN.md](EDITIONS.zh-CN.md)）。

## 核对下载的文件

可选。每个发布版本都有一个 `SHA256SUMS` 文件，每个下载文件占一行。算出你下载的文件的校验和，与该文件名
对应的那一行比较：

```bash
shasum -a 256 RoomScope-Desktop-macOS-arm64.dmg          # macOS
sha256sum RoomScope-Terminal-Linux-x86_64.tar.gz         # Linux
```

```powershell
Get-FileHash .\RoomScope-Desktop-Windows-x64-Setup.exe   # Windows PowerShell（SHA256）
```

一致说明文件就是发布页上附带的那个，但不能证明是谁构建的；这正是代码签名将来要补上的。

## 未签名构建的警告

**当前构建是未签名的开发版 / 预发布版构建。** macOS 应用只有临时签名（ad hoc），没有经过 Apple 公证；Windows 文件
没有 Authenticode 签名。所以系统无法确认发布者，会警告一次：

| 系统 | 你会看到 | 怎么做 |
| --- | --- | --- |
| macOS 15 及更新 | *Apple 无法验证“RoomScope”是否包含……恶意软件* | **完成**，然后 **系统设置 → 隐私与安全性 → 仍要打开**（[详细步骤](#macos-首次打开)） |
| macOS 14 | *无法打开“RoomScope”，因为 Apple 无法检查其是否包含恶意软件*（或 *……来自身份不明的开发者*） | 按住 Control 键点按 → **打开**，或者用上面的“隐私与安全性”方法 |
| Windows 10 / 11 | *Windows 已保护你的电脑*（SmartScreen） | **更多信息 → 仍要运行** |
| 开启了“智能应用控制”的 Windows 11 | 应用被直接阻止，没有“仍要运行” | 这种情况下未签名构建无法运行；在有签名构建之前，请使用 [Python 安装](#python-wheel-和源码包) |

构建来自公开的 [release workflow](https://github.com/jingyemingyue/RoomScope/actions/workflows/release.yml)，每个构建都记录了
它所基于的提交（**帮助 → 用于问题报告的环境报告**）。签名计划在 1.0 之前完成（[RELEASE_PLAN.zh-CN.md](RELEASE_PLAN.zh-CN.md)）。

## 更新

从同一个页面下载新文件，然后：

* **macOS：** 退出 RoomScope，打开新的 DMG，再把 RoomScope 拖到“应用程序”上，选 **替换**。新构建可能会再出现一次
  首次打开的警告。
* **Windows 安装程序：** 运行新的 `RoomScope-Desktop-Windows-x64-Setup.exe`，它会替换已安装的版本。
* **Windows ZIP / Linux / 终端版：** 删除旧文件夹，解压新的压缩包。
* **wheel：** 在同一个虚拟环境里运行 `pip install --upgrade "./roomscope-<新版本>-py3-none-any.whl[gui]"`。
* **开发者安装：** `git pull`，然后再运行一次 `pip install -e ".[dev,gui]"`。

`~/.roomscope` 里的设置、最近会话列表和日志会保留，你保存的会话文件夹也不会被改动。

## 卸载

* **macOS：** 退出 RoomScope，把“应用程序”里的 **RoomScope** 拖到废纸篓。
* **Windows 安装程序：** **设置 → 应用 → 已安装的应用 → RoomScope → 卸载**，或者开始菜单 → *卸载 RoomScope*。
* **Windows ZIP / Linux / 终端版：** 删除解压出来的文件夹。
* **Python：** `pip uninstall roomscope`，或者直接删除虚拟环境文件夹。

如果还想删除 RoomScope 的设置、日志、最近会话列表和字体缓存，删除个人文件夹里的 `.roomscope` 文件夹
（macOS / Linux 为 `~/.roomscope`，Windows 为 `%USERPROFILE%\.roomscope`；可用 `ROOMSCOPE_HOME` 改变位置）。你保存的
测量结果仍在你保存的位置。

## 故障排查

| 问题 | 怎么做 |
| --- | --- |
| macOS：*Apple 无法验证“RoomScope”……* | 未签名构建的正常现象：见 [macOS 首次打开](#macos-首次打开)。 |
| macOS：*“RoomScope”已损坏，无法打开* | 下载不完整或文件被改动过。删除后重新下载，并[核对校验和](#核对下载的文件)。不要绕过这个提示。 |
| macOS：提示*这种类型的 Mac 不支持*，或在 macOS 13 及更早版本上无法启动 | 使用与你的 Mac 相符的 DMG；需要 macOS 14 或更新。 |
| macOS / Windows：没有麦克风输入 | 允许麦克风访问（[macOS](#麦克风权限)、[Windows](#windows-上的麦克风权限)），然后用 **帮助 → 用于问题报告的环境报告** 查看 RoomScope 识别到了什么。 |
| Windows：双击没反应，或提示缺少 DLL | 先完整解压 ZIP（**全部解压缩…**），并让 `_internal` 与 `roomscope-gui.exe` 在一起。 |
| Windows：没有“仍要运行”按钮 | “智能应用控制”或公司策略阻止了未签名应用；见[上面的表格](#未签名构建的警告)。 |
| Linux：`libEGL.so.1`、`libportaudio` 或 *xcb* 插件报错 | 安装[系统库](#linux)。 |
| Linux：图表里的中文显示成方框 | `sudo apt install fonts-noto-cjk` |
| `roomscope gui` 提示*当前安装的是 RoomScope 终端版* | 终端版没有图形界面；请下载桌面版（两个版本都有命令行）。 |
| macOS：*无法打开“roomscope”，因为无法验证开发者*（终端版） | 清除一次下载标记：`xattr -dr com.apple.quarantine roomscope-terminal`（见[终端版](#终端版)）。 |
| Windows：`roomscope.exe` 打开后立刻关闭 | 它是命令行程序：改为双击 `RoomScope Terminal.cmd`，或在命令提示符里运行它。 |
| `roomscope gui` 提示无法加载 PySide6 | 安装界面组件：`pip install "PySide6_Essentials>=6.6"`（或者带 `[gui]` 重新安装 wheel）。 |
| `pip install roomscope` 找不到，或者装到了别的东西 | RoomScope 还没有发布到 PyPI；请使用 [wheel](#用发布页的-wheel-安装)。 |
| 其他问题 | 提交一个 [问题报告](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug-zh-CN.yml)，并粘贴 **帮助 → 用于问题报告的环境报告**（或 `roomscope doctor` 的输出）。不会自动发送任何内容。 |

下一步：[用户指南](user-guide/zh-CN.md)带你完成第一次测量。
