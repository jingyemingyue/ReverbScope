# ReverbScope 发布计划（中文摘要）

[English](RELEASE_PLAN.md) | **简体中文**

英文版 [RELEASE_PLAN.md](RELEASE_PLAN.md) 为准，本文只是摘要。2026-09-24 采纳。

没有日期：达到退出条件才发版（ARCHITECTURE_V1.md §10）。

## 1. 现状

* `main` 已经包含 v0.1 基础 + 0.2（重开与对比）+ 0.3（信任测量链）+ 0.4（面向所有人）+ 1.0-rc 的纯软件部分。四个里程碑 PR（#5、#6、#7、#8）在 2026-09-24 审查后合并，审查发现记录为 issue #9–#16。
* 还没有任何 tag 或已发布的 Release（v0.4.1 是草稿）。仓库已于 2026-09-24 公开。**更新（2026-09-27）：** v0.4.1 已准备好作为第一个面向早期测试者的*公开*预发布版本：README 和 [INSTALLATION.zh-CN.md](INSTALLATION.zh-CN.md) 以下载为先，发布说明以“选择版本（Choose your edition）”和“已知限制”开头，候选构建已核对（§3c）。**更新（2026-09-29）：** 每个平台都提供桌面版和终端版（[EDITIONS.zh-CN.md](EDITIONS.zh-CN.md)），`CHANGELOG.md` 的 `[Unreleased]` 条目已并入 `[0.4.1]`，草稿的说明因此涵盖这个预发布版本的全部内容。维护者发布草稿后它才公开；这里的任何改动都不会发布它。**更新（2026-09-30）：** 候选版本已进入 `main`：按 PR #24 → #22 → #21 的顺序用合并提交合并（不 squash、不 rebase），`main` = `c5fe692`，其文件树与 #24 的 head 完全相同。该提交上 CI #81 和 Release #34 全绿，Release #34 用这个提交的 14 个文件刷新了 v0.4.1 草稿（STATUS 快照 32）。PR #23 已作为被 #24 取代而关闭。草稿仍未发布。**收尾更新（2026-09-30）：** PR #25、#26 也已合并；`d97822a` 上的 CI #87 和 Release #38 全绿，同一个草稿已用该提交的 14 个文件和补全测试限制的说明刷新（STATUS 快照 33），仍未发布。**已发布（2026-09-30）：** 该草稿已作为预发布版本公开，未标为 latest。tag `v0.4.1` 指向 `d97822a`，14 个附件保留。在测试者自己的电脑上安装（清单第 3 步）仍未做。
* 需要人在真实房间完成的事情都没做：硬件矩阵（HARDWARE_TESTS.md）没有一格 PASS，验证活动（VALIDATION.md）没有跑。维护者近期没有测量设备，所以这些排在最后，也可以在开源之后由贡献者补。
* **软件 beta（2026-10-01）：** `0.5.0b1` 打包 0.4.1 之后落地的内容（早期/后期能量、录音配置的清晰度提示、摆放示意图、桌面与命令行打磨）。它**不**满足下面 0.5.0 那一行：硬件矩阵没有 PASS，因此不切 0.5.0。发布 `v0.5.0b1` 不会重新发布 `v0.4.1`。
* 签名证书、PyPI 项目名与可信发布都是维护者决定，目前未定；仓库已于 2026-09-24 公开。

## 2. 版本阶梯

| 版本 | 目的 | 切版前必须成立 | 不声称 |
| --- | --- | --- | --- |
| **0.4.0** | 第一个预发布：把 `main` 上的东西做成草稿 Release 和未签名安装包，供维护者自测 | 三个系统、Python 3.12–3.14 的 CI 全绿；ruff、mypy、schema、打包门禁通过；许可证包含 LGPL-3.0 / GPL-3.0 / PortAudio 原文；CHANGELOG 有 `[0.4.0]` 节；STATUS 有带日期的快照 | 任何硬件结果；真人安装过安装包；PyPI；公开可用 |
| **0.4.x** | 社区硬件验证之前的软件就绪阶段（维护者于 2026-09-24 定义）：审查后续 #9–#17（0.4.1 全部关闭）、打包、设备诊断、界面、DAW 指南和社区报告模板 | 发布提交上 CI 与发布工作流全绿；每个新行为都有合成或脚本化测试；CHANGELOG 写明改动；不声称任何硬件或 DAW 结果 | 任何硬件或 DAW 结果；签名；PyPI |
| **0.5.0b1** | 软件 beta：发出 0.4.1 之后落地的单话筒算法和桌面呈现，仍然不声称硬件结果 | 发布提交上 CI 与发布工作流全绿；每个新行为都有合成测试；CHANGELOG 写明版本；说明里写明这不是 0.5.0 | 任何硬件或 DAW 结果；0.5.0 的退出条件；签名；PyPI |
| **0.5.0** | “有人用过”：Standalone 和 DAW 流程第一次在真实硬件上跑通 | 至少一个平台上硬件矩阵每格都有带日期的 PASS；#12、#13、#14、#15 关闭 | 验证活动；API/schema 冻结；签名 |
| **1.0.0rc1** | 冻结并证明 | ARCHITECTURE_V1.md §3.1 的 MUST 项无一开放：硬件矩阵每个平台至少跑过一次、验证活动连数据一起发布、签名或维护者明确决定不签、公开仓库清单执行完、API 与 schema 冻结 | — |
| **1.0.0** | 正式版 | 只含候选版之后的修复；发布说明写明验证结果和已知限制 | — |

## 3. 一次发布怎么产生

流水线是 `.github/workflows/release.yml`，由 `pyproject.toml` 里的版本号驱动，最后一步始终由维护者点击。

> **工作流状态（2026-09-24）**：按版本号发布的工作流自 PR #18 起已在 `main`
> 上；v0.4.1 草稿 Release 就是由它创建的。只要 `v0.4.1` 还没有 tag，`main`
> 上的 `pyproject.toml`、工作流、`packaging/`、`scripts/smoke_bundle.py`、`scripts/release_draft.py`、
> `scripts/inno_chinese_messages.py` 或 `src/reverbscope/__main__.py` 一有变化，草稿就会被刷新。Windows 任务每次都会构建并安装
> `ReverbScope-Desktop-Windows-x64-Setup.exe`，每个任务还会构建本平台的终端版。发布前核对 `main` 最新一次运行和草稿附件。
>
> **草稿如何刷新**（`scripts/release_draft.py`）：每次刷新都替换*全部*附件、
> 正文、tag 名和目标提交，草稿里只有目标提交那一次成功运行产出的 14 个文件（两个版本的 9 个下载文件、wheel、sdist、一个 `SHA256SUMS`、SBOM 和锁定文件）；
> 旧工作流留下的、现在已不再产出的文件名（`ReverbScope.dmg`、`SHA256SUMS-macOS`
> 等）会被删掉。遇到以下情况任务直接失败、不做任何修改：`v<版本>` 已发布、
> 有两个匹配的草稿、`v<版本>` tag 指向别的提交、草稿里有它不认识的文件（例如
> 手动上传的文件：删掉它，或不再重跑工作流直接发布）。只改 `src/` 不会触发
> Release 工作流；需要在 `main` 上手动运行（**Actions → Release → Run
> workflow**），草稿才会按最新提交重建。
> 第一次在 `main` 上执行这套刷新的是 `c5fe692` 上的 Release #34（2026-09-30）：它原地更新了已有草稿 395349087（替换 4 个文件、
> 删除 6 个旧文件名、上传 14 个文件），*Verify the draft* 步骤通过。之后如果提交没有碰上面这些路径（例如只改 `docs/`），
> 草稿仍停在 `c5fe692`，发布时 tag 打在 `c5fe692` 上，也就是构建这些文件的提交。
> 后来 PR #26 修改了发布说明头，Release #38 已从 `d97822a` 刷新同一个草稿。之后仅修改文档的收尾记录不触发 Release，
> 所以草稿目标仍为 `d97822a`，发布时 tag 会打在这个实际构建附件的提交上（STATUS 快照 33）。

1. **在 `main` 上准备发布提交**：把 `project.version` 改成新版本（不带 `.dev`），把 CHANGELOG 的 `[Unreleased]` 挪到 `## [版本] - 日期` 下，在 `docs/STATUS.md` 加一条写明“实际跑了什么”的快照，依赖版本有变时复查 DEPENDENCIES.md §3–§4。提交并推送。
2. **CI 自动开草稿**：`pyproject.toml` 在 `main` 上变了、且还没有 `v<版本>` 这个 tag，工作流就会跑 lint/类型检查/测试，构建 sdist 和 wheel，在三个系统上构建未签名安装包（许可证包 → PyInstaller → 剥掉 GPL-only Qt 模块和 ASIO DLL → 门禁 → 冒烟测试 → 打包 → 校验和），生成 SBOM，然后打开或刷新名为 `v<版本>` 的**草稿** Release，正文是发布说明（`packaging/release-notes-header.md` 包着 CHANGELOG 对应段落），附件是那 14 个文件。**此时还没有 tag。** 带 `.dev` 的版本不会开草稿。
3. **维护者决定**：从草稿下载安装包在真机上试；发布（publish）或删除草稿。发布这一下会在发布提交上创建 tag `v<版本>` —— 这就是项目简报里保留给维护者的“正式 Release”决定。
4. **tag 触发的运行**：tag 被创建后再跑一遍质量门禁；只有当仓库变量 `REVERBSCOPE_PUBLISH_PYPI` 为 `true`、`pypi` 环境和 PyPI 可信发布都配好了，才会把 wheel 传到 PyPI。在此之前不会有任何东西到 PyPI。

由此得出的规则：`pyproject.toml` 是版本号的唯一来源；tag 名与它不一致时工作流失败；tag 只来自发布草稿或维护者自己推送；已发布的历史永不重写。

### 3a. 没有 GitHub Actions 额度时

私有仓库消耗自己的 Actions 分钟数，macOS 运行器按十倍计。额度用完后，任务会在几秒内失败且没有分配运行器（没有步骤、没有日志）。可选做法（从省钱到省事）：

1. **本地构建。** `scripts/build_release.py` 在当前机器上执行与发布工作流 bundle 任务相同的步骤，并在 `dist/` 中生成相同的文件名。每个平台运行一次：Apple 芯片 Mac（`ReverbScope-Desktop-macOS-arm64.dmg`、`ReverbScope-Terminal-macOS-arm64.tar.gz`）、有条件时 Intel Mac（`ReverbScope-Desktop-macOS-x86_64.dmg`、`ReverbScope-Terminal-macOS-x86_64.tar.gz`）、装有 Inno Setup 6 的 Windows（`ReverbScope-Desktop-Windows-x64-Setup.exe`、`ReverbScope-Desktop-Windows-x64.zip`、`ReverbScope-Terminal-Windows-x64.zip`）以及 Linux x86_64（`ReverbScope-Desktop-Linux-x86_64.tar.gz`、`ReverbScope-Terminal-Linux-x86_64.tar.gz`）；在其中一台上加 `--python-dist` 生成 wheel 和 sdist。运行前按脚本文档安装 `requirements/bundle.lock`、`dev` 与 `gui` 附加依赖、`pyinstaller==6.22.3` 和 `build`；版本不一致时脚本会拒绝，除非加 `--allow-unlocked`。脚本会运行测试、许可证包、`--strip --require-licenses` 门禁和冒烟测试；在 macOS 上还会做临时签名，并从 DMG 挂载、复制和启动应用。在 Windows 上它只编译安装程序，不像工作流那样安装、冒烟测试和卸载（那会改变这台电脑）；发布本地构建的安装程序前请手动完成这三步。
2. **手动发布。** 在 Releases 页面创建或编辑草稿 `v<version>`（tag 为 `main` 上发布提交的 `v<version>`，勾选 *pre-release*），粘贴说明（`packaging/release-notes-header.md` 中把 `{version}` 替换，并在 `{changes}` 处放入 CHANGELOG 对应段落），上传第 1 步的所有文件，以及由每台机器的 `SHA256SUMS-*` 各行合成的一个 `SHA256SUMS`，然后发布。PyPI 任务需要 Actions，没有它就不会上传 PyPI。
3. **把仓库设为公开**（§5）：公开仓库使用 GitHub 托管的标准运行器是免费的，工作流即可照常运行。已于 2026-09-24 公开，此后工作流一直在 GitHub 运行器上运行。

本地构建的版本只经过了该脚本在那台机器上执行的检查；`docs/STATUS.md` 记录哪台机器构建了哪些文件。

### 3b. macOS 签名：现在，以及有 Developer ID 之后

**现在**应用只做临时（ad hoc）签名，它只封装应用包：不是 Developer ID 签名，没有公证，首次打开会被 Gatekeeper 拦截（步骤见用户指南）。`packaging/macos/sign_app.sh` 按 Apple 对分发代码的要求由内向外签名 [A1][A2]：先签 `Contents/Frameworks` 下每个独立的 Mach-O 文件，再按由深到浅的顺序签每个嵌套 `.framework`，最后签应用本身；`codesign --deep` 只用于验证，因为 Apple 不建议用它签名 [A1][A3]。发布的应用不启用 hardened runtime，也没有 entitlements。

**在 CI 中演练。** 在两个 macOS 运行器（arm64、x86_64）上，发布任务用 `sign_app.sh --runtime` 对应用副本签名：启用 hardened runtime 并使用 `entitlements-adhoc.plist`。该副本必须能启动（GUI 冒烟测试、fake 后端测量），并且 `reverbscope doctor` 必须能创建 cffi 回调，这是 PortAudio 在音频线程中调用 ReverbScope 的机制。各 entitlement 的理由：

| 键 | 原因 | 来源 |
| --- | --- | --- |
| `com.apple.security.device.audio-input` | hardened runtime 下的 Core Audio 输入（话筒）；缺少它系统会终止应用 | [A4][A5] |
| `com.apple.security.cs.allow-unsigned-executable-memory` | python-sounddevice 用 cffi 的 `ffi.callback`（ABI 模式）创建流回调；cffi 文档要求在 macOS 上提供此键，而 Apple 的 x86_64 libffi 在不使用 `MAP_JIT` 的情况下映射可写且可执行的内存 | [A6][A7] |
| `com.apple.security.cs.disable-library-validation`（仅演练文件） | 临时签名没有 Team ID，库验证会拒绝应用自己的库。Developer ID 构建用同一个 Team ID 签署所有内容，不需要此键 | [A8] |

`entitlements.plist`（Developer ID 使用的文件）只含前两个键，永远不含公证会拒绝的 `get-task-allow` [A9]。

**有了 Developer ID Application 证书之后**（维护者决定，§5）。发布工作流里已经写好这些步骤；只有下表六个仓库 secret 全部存在时才执行，所以社区和 fork 构建仍是临时签名。它们从不在拉取请求上运行；只设置了部分 secret 会让构建失败，而不是悄悄发出临时签名的 DMG。**目前都还没有运行过**：还没有证书。

1. `packaging/macos/import_certificate.sh` 把 `.p12` 导入临时钥匙串，只接受 `Developer ID Application` 身份；作业结束时（包括失败时）删除该钥匙串。
2. `sign_app.sh dist/ReverbScope.app --identity "$MACOS_SIGNING_IDENTITY"` 重新签名：顺序相同，每一项加 `--timestamp`，应用本身加 `--options runtime` 和 `entitlements.plist` [A2][A9]；随后检查 runtime 标志、Developer ID 签发者和时间戳，并对签名后的应用做冒烟测试。
3. `packaging/macos/notarize_dmg.sh` 用 `--timestamp` 签署 DMG [A10]；
4. 用 App Store Connect API 密钥执行 `xcrun notarytool submit --wait`，即使成功也打印 `notarytool log`，状态不是 `Accepted` 就失败 [A11][A12]；
5. staple 公证票据（`stapler staple`、`stapler validate`），再对 DMG 执行 `spctl -a -t open --context context:primary-signature`、对挂载后的应用执行 `spctl -a -t exec` [A12][A13]。
6. SHA-256 在 staple 之后计算（staple 会改变 DMG）。

| 仓库 secret | 内容 | 来源 |
| --- | --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | 含私钥的 Developer ID Application 证书，导出为 `.p12` 后做 base64 编码 | Apple Developer 账户 ▸ Certificates ▸ `+` ▸ Developer ID Application（仅 Account Holder 可建），再用“钥匙串访问”导出 `.p12` [A14] |
| `MACOS_CERTIFICATE_PASSWORD` | 导出 `.p12` 时设置的密码 | 你自己 |
| `MACOS_SIGNING_IDENTITY` | 身份名称，例如 `Developer ID Application: Jane Doe (AB12CD34EF)` | 导入证书后运行 `security find-identity -v -p codesigning` |
| `APPLE_API_KEY_P8_BASE64` | App Store Connect API 密钥（`AuthKey_<id>.p8`），base64 编码 | App Store Connect ▸ 用户和访问 ▸ 集成 ▸ 团队密钥 ▸ `+`（`.p8` 只能下载一次）[A15] |
| `APPLE_API_KEY_ID` | 该密钥的 Key ID | 同一页面 |
| `APPLE_API_ISSUER_ID` | 密钥列表上方的 Issuer ID | 同一页面 |

**为什么是两个 DMG 而不是一个 Universal 应用。** PyInstaller 只有在所有收集到的二进制文件本身都是 universal2 时才能构建可用的 `universal2` 应用 [A16]。`requirements/bundle.lock` 固定的版本（2026-09-27 在 PyPI 核对）中，NumPy 2.5.3、SciPy 1.18.1、matplotlib 3.11.2、Pillow 12.3.0、contourpy 1.4.0、cffi 2.1.1 和 soundfile 0.14.0 只发布分开的 `arm64` 与 `x86_64` macOS wheel，所以每个架构各发一个 DMG，并在该架构的运行器上构建和测试。

没有证书时 CI 无法证明的内容：Developer ID 签名、共享 Team ID 下的库验证、安全时间戳、公证、staple、Gatekeeper 放行，以及话筒权限提示。

Windows：安装程序和可执行文件没有 Authenticode 签名，首次运行时 SmartScreen 会警告（见用户指南）。这是 0.x 预发布版本的已知限制，不是错误；是否签名属于同一个 §5 决定。有证书后：先用 `signtool sign /fd sha256 /tr <时间戳 URL> /td sha256` 签署 `dist\reverbscope\*.exe`，再用 `iscc "--signtool=signtool=signtool.exe sign … $f" /DSignToolName=signtool` 编译安装程序，让 Inno Setup 签署安装程序及其卸载程序（[W1][W2][W3]；`packaging/windows/reverbscope.iss`）。尚未运行过。

§3b 来源见英文版 [RELEASE_PLAN.md](RELEASE_PLAN.md) §3b 的 [A1]–[A16]、[W1]–[W3]。

### 3c. 发布 v0.4.1：第一个公开预发布版本

README 的 **下载** 按钮指向的就是 v0.4.1。在 `v0.4.1` 还没有 tag 之前，`main` 上的每次相关运行都会重建草稿，所以草稿里的
文件总是来自最新 `main` 提交的同一次运行；由于这个版本号从未发布过，版本仍为 0.4.1。

2026-09-27 在候选构建（Release 运行 #23，PR #21 head `b753e17`）上核对了：全部校验和；wheel 在全新虚拟环境中（非可编辑安装）
的 CLI、假后端测量、中文输出和 GUI 冒烟；源码包能构建出相同的 wheel；`twine check`；两个 DMG 的内容、架构、Info.plist 和
动态库路径（在 macOS 上的挂载、安装和启动由工作流在 macOS 26 / 15 运行器上完成，不是真人）；Windows ZIP 的结构（只有工作流在
Windows 运行器上启动过）；Linux 包在空环境中的冒烟；密钥与私人路径扫描；各处版本号均为 0.4.1。详见英文版 §3c 和 STATUS 快照 30。这些检查针对 `b753e17` 构建出的文件，文件名也是那次运行的旧名字（当时还没有桌面版 / 终端版之分，也没有终端版压缩包）。之后到 #24 的 head `cf27b30` 为止又加入了 14 个提交（包括命令行输出改进 `0f5418e` / `f5eb961`、并入 #23 首次使用体验的 `cd45bf9`、桌面版 / 终端版拆分 `bcea79a`、发布文件修正 `cccc682` / `f893cc7` 和 `cf27b30` 的导出器修复），由 CI 和 Release 工作流在各平台上的冒烟测试覆盖（最近一次：`c5fe692` 上的 Release #34，STATUS 快照 32），不在这次下载检查之内：发布前请在草稿文件上重复 wheel 检查和下面的第 3 步。

**发布清单（维护者的操作）：**

1. 把候选分支合并到 `main`，等该提交上的 **CI** 和 **Release** 都变绿；Release 会用该提交的 14 个文件和新的说明刷新 v0.4.1 草稿。
2. 在草稿上核对：目标提交是那个绿色的 `main` 提交；14 个附件齐全（桌面版 5 个、终端版 4 个、wheel、sdist、`SHA256SUMS`、SBOM 和锁定文件）；说明以 *ReverbScope v0.4.1 — Early public pre-release for testing* 开头。

   **第 1、2 步在 PR #25、#26 合并后于 2026-09-30 重新核验**（STATUS 快照 33）：发布提交为 `d97822a`，CI #87 和 Release #38 全绿；草稿目标为 `d97822a`，附件正好是上面 14 个，说明与该提交修正后的发布说明头和 CHANGELOG 一致，工作流的 *Verify the draft* 步骤已把文件名、大小和摘要与本次运行的文件逐一比对。之后仅修改文档的提交不会改变草稿目标。第 3 到 5 步由维护者完成。
3. 建议发布前：下载适合你的 Mac 的 DMG，按 [INSTALLATION.zh-CN.md](INSTALLATION.zh-CN.md) 安装并打开一次（包括 Gatekeeper 步骤）。这是任何工作流都做不到的一项检查。
4. 保持勾选 **Set as a pre-release**，不要勾选 *Set as the latest release*，点 **Publish release**。发布会在目标提交上创建 tag `v0.4.1`；PyPI 仍然关闭（§3d）。
5. 用无痕窗口打开 <https://github.com/jingyemingyue/ReverbScope/releases>，确认能看到 v0.4.1 及其附件。README 链接的是这个页面而不是 `/releases/latest`，因为 GitHub 的 *latest* 永远不会指向预发布版本（只有预发布时会跳转到 `/releases`，API 返回 404）。

### 3d. PyPI 就绪情况（2026-09-27 检查，未发布）

0.4.x 不上传 PyPI；第一批公开测试者通过 GitHub Releases 获取。`reverbscope` 这个名字在 2026-09-27 仍未被占用（未保留）；wheel 和
源码包的元数据通过 `twine check`；可信发布已在 `release.yml` 中接好，但还缺 PyPI 端的 trusted publisher、带审批人的 `pypi` 环境和
仓库变量；`pypa/gh-action-pypi-publish` 在可信发布下默认上传 PEP 740 证明。**尚未就绪：** `README.md` 里有 38 个相对链接和一张截图，在
pypi.org 上会失效，首次上传前需要一份使用绝对链接的 README。在真正发布到 PyPI 之前，任何文档都不能让用户运行 `pip install reverbscope`。

## 4. 每次发布都适用的门禁

CI 全绿（lint、mypy、文档链接检查、文档站点构建、`check_src_safety.py`、schema、测试矩阵、`core`/`models` 85% 覆盖率、打包、已安装 Essentials 的 GPL 门禁）；发布工作流全绿（`--strip --require-licenses` 门禁、每个系统的冒烟测试）；DEPENDENCIES.md §6 没有影响所发二进制的 UNKNOWN / NEEDS REVIEW；STATUS 如实写明跑了什么、没跑什么，硬件格保持空白直到有人填上日期和声卡型号；CHANGELOG 有该版本段落，审查发现的夸大说法在同一版本里更正（0.4.0：中文目录只覆盖七个 profile 中的三个，见 #14，0.4.1 已补全）。

## 5. 仍待维护者决定

公开仓库（已于 2026-09-24 公开；§9.1 清单中其余仓库设置未在此核对）；Apple Developer ID + 公证、Windows 签名，或明确决定不签名发 1.0；PyPI 注册 `reverbscope`、配可信发布、建 `pypi` 环境、设 `REVERBSCOPE_PUBLISH_PYPI=true`、为 PyPI 准备使用绝对链接的 README（§3d）；把 v0.4.1 草稿发布为第一个公开预发布版本（已于 2026-09-30 完成：预发布、非 latest，tag `v0.4.1` 在 `d97822a`，14 个附件；自己电脑上的安装仍未做）；验证活动的房间、参考工具（REW 只作对比仪器）和执行人；是否要求 DCO 签署；Dependabot 的 #3 / #4 等 v0.4.1 发布之后再处理（收尾期间不升级 GitHub Actions 的大版本），届时在它重新 rebase 到 SHA 固定的工作流并且 CI 绿之后合并。

## 6. 2026-09-24 审查后续（issue）

#9 频响对比先插值再平滑（混叠）；#10 `analyze-ir` 无测试；#11 会话加载跟随绝对路径；#12 环回 FIR 窗把补偿后的响应提前约 5 ms；#13 PortAudio 在实时回调里报进度、回调异常被吞；#14 中文目录不全、安全提示未翻译、`.mo` 未随包发布；#15 ISO 3382-2 表 1 未注明来源、engineering 等级不检查话筒数；#16 `check_src_safety.py` 漏检、覆盖率数字未记录。#17 打包门禁按文件名认不出虚拟键盘的 QML 插件。

**更新（2026-09-24 稍晚）：** 以上九项都已在分支 `v0.4.1-review-followups` 修好（版本号 0.4.1，每项都有在 0.4.0 上会失败的合成测试，见 CHANGELOG `[0.4.1]`）。因为 #17 必须在发布任何安装包之前关闭（§4），0.4.0 不再单独发 Release：这个 PR 在 CI 全绿后合并，第一个草稿 Release 就是 v0.4.1。

## 7. 本计划不做的事

不公开仓库、不创建正式 Release、不改许可证、不手动推 tag、不重写历史、不声称任何硬件结果。这些要么是维护者的一次点击，要么需要有人站在房间里。
