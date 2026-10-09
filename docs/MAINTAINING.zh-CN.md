# 维护 ReverbScope

写给接手维护的人：哪个分支是哪条线、自动化自己会做什么、哪些事只有维护者能做、以及某项检查变红时该怎么办。本文不假设有任何助手，每一步都写明对应的文件或页面。请与 [RELEASE_PLAN.zh-CN.md](RELEASE_PLAN.zh-CN.md)（两条线为何存在、发布如何产生、0.5.0 的门槛；英文全文 [RELEASE_PLAN.md](RELEASE_PLAN.md)）、[CONTRIBUTING.md](../CONTRIBUTING.md)（改动必须遵守的规则、从社区报告到回归测试的流程，英文）、[OFFLINE_CHECKS.md](OFFLINE_CHECKS.md)（没有硬件时能检查什么，英文）和 [API_STABILITY.md](API_STABILITY.md)（哪些东西不能悄悄改变，英文）一起阅读。英文版：[MAINTAINING.md](MAINTAINING.md)。

## 1. 两条线

| 线 | 分支 | `pyproject.toml` 中的版本 | 允许进入的改动 |
| --- | --- | --- | --- |
| 测试版（开发线） | `main` | `0.5.0b2`，之后 `0.5.0b3`…… | 一切：修复、新功能、交互、文档 |
| 候选版 | `release/0.5.0` | `0.5.0rc1`，之后 `rc2`……直到 `0.5.0` | 只允许正确性、崩溃、打包、跨平台、硬件/DAW 兼容性、文档、本地化和发布工程方面的修复，能写测试的都带回归测试（见 RELEASE_PLAN §2a） |

保持两条线一致的规则：

* 两条线都需要的修复只提交一次，通过 `git merge` 或 `git cherry-pick -x` 同一个提交到达另一条线，绝不手工重打。候选线上的 bug 先在候选线修，同一次工作中再向前合并到 `main`。
* 除此之外，没有任何改动从 `main` 进入候选线。新功能、命令行重新设计、算法实验、依赖升级都留在 `main`，等下一个候选系列再说。
* 已发布的历史永不重写：不对 `main`、`release/**` 或已发布 tag 强推；合并使用 merge commit（每个 PR 的合并提交就是冲突如何解决的记录）。
* 只有在真实设备上满足 RELEASE_PLAN §2b 的门槛、并由维护者发布时，候选版才成为 `0.5.0`。

## 2. 自动运行的部分

两个工作流都在 `.github/workflows/` 下；每个 action 都固定到提交 SHA，版本写在注释里。

**CI**（`ci.yml`）：每个 pull request、以及推送到 `main` 和 `release/**` 时运行，九个作业必须全绿才能合并：

| 作业 | 证明什么 |
| --- | --- |
| Lint and type-check | `ruff check`、`ruff format --check`、严格 `mypy`（只装 `dev` 附加依赖，没有 PySide6 的类型存根：只有在存根存在时才通过类型检查的代码会在这里失败）、`scripts/check_doc_links.py`、`scripts/check_cli_docs.py`、文档站构建、`scripts/check_src_safety.py`（`src/` 下无网络导入、无 shell 调用） |
| JSON Schemas | schema 测试，以及 `reverbscope schema <名称>` 输出与随包文件逐字相同 |
| Tests（Ubuntu 3.12 / 3.13 / 3.14、macOS 3.12、Windows 3.12） | 完整测试套件（离屏）；Ubuntu 3.12 上附带 `core` 与 `models` 85 % 分支覆盖率门槛；之后是伪后端的 Standalone 流程和 `examples/synthetic_measurement.py` |
| sdist and wheel | `python -m build`，wheel 可安装，`reverbscope --help` 可运行 |
| License bundle and GPL-module gate | `scripts/build_license_bundle.py` 能解析每个包的许可证；安装的 PySide6 只有 Essentials（没有 GPL-only 的 Qt 模块） |

**Release**（`release.yml`）：当推送到 `main` 或 `release/**` 且触及发布文件（`pyproject.toml`、`packaging/`、打包脚本、工作流本身、`requirements/`）、推送 `v*` tag、pull request 触及这些文件、或手动运行（**Actions → Release → Run workflow**）时运行。它运行质量作业，构建 sdist 与 wheel、四个平台的安装包（Linux、macOS arm64、macOS x86_64、Windows，每个平台桌面版与终端版各一），对每个包做冒烟测试（`scripts/smoke_bundle.py`），安装、冒烟并卸载 Windows 安装程序，构建并检查两个 DMG，生成 SBOM，核对精确的文件集合（`scripts/release_draft.py stage`），并在 `main` 或 `release/**` 上、且 tag `v<版本>` 尚不存在时，打开或刷新**草稿** Release `v<版本>`，恰好 14 个文件。pull request 的运行不会生成草稿；只改文档的推送不会构建任何东西。

**Pages**（`pages.yml`）在仓库设置中启用 Pages 后发布 `site/`。

**Dependabot**（`.github/dependabot.yml`）为固定 SHA 的 GitHub Actions 开 pull request。一次只处理一个：`upload-artifact` / `download-artifact` 的大版本会改变 Release 工作流在作业之间传递文件的方式，所以只有当该 PR 自己的 *Release* 运行全绿（工作流会在改动它的 PR 上运行）、且之后从 `main` 刷新的草稿仍然恰好有 14 个文件时，才合并这类升级。

## 3. 只有维护者能做的事

* **发布一个版本。** 在 Releases 页打开草稿 `v<版本>`，读一遍说明，至少下载一个安装包并在真实机器上启动，然后 **Publish release**（测试版和候选版都勾选 *pre-release*）。发布会创建 tag；tag 的运行会重复所有门槛，并且只在仓库变量 `REVERBSCOPE_PUBLISH_PYPI` 为 `true` 且 `pypi` 环境存在时上传 PyPI（RELEASE_PLAN §3）。不要发布目标提交不是该线最新提交的草稿：草稿由下一次 Release 运行重建，而只改文档的推送不会触发它——草稿落后时手动运行工作流。
* **切下一个候选版**（`rc2`……）：在 `release/0.5.0` 上一个提交，设置 `project.version`、重命名 CHANGELOG 小节、添加 STATUS 快照；推送后 Release 运行打开新草稿。只有当这个提交带有修复时才把它合并进 `main`；版本号本身留在候选线。
* **切下一个测试版**：在 `main` 上同样形状的提交，版本 `0.5.0b3`，把 `[Unreleased]` 条目移到新标题下。
* **仓库设置**（命令行和工作流都改不了）：`main` 的 ruleset（要求九个 CI 作业、禁止强推和删除、要求 pull request，单人维护时 0 个审批）、`release/**` 同样、Pages、描述、topics、主页；macOS Developer ID 密钥（RELEASE_PLAN §3b）。
* **关闭或合并 pull request**，对报告做决定（§5），只根据 issue 填写 [HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md) 的结果日志。

## 4. 每次推送之前

在本机运行 CI 运行的东西（不含测试套件一两分钟，含测试套件约十分钟）：

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gui]" build
ruff check . && ruff format --check .
mypy
python scripts/check_doc_links.py && python scripts/check_cli_docs.py && python scripts/check_src_safety.py
python scripts/build_docs_site.py --out /tmp/reverbscope-site
QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85
python -m build
```

然后只推送一次。每次向 pull request 推送都花费一次 CI 运行（约 15 个 runner 分钟，macOS 按加权计）；如果改了发布文件，再加一次 Release 运行（约 40 个 runner 分钟）。几分钟内的连续推送会取消旧的运行；推送到 `main` 和 tag 不会被取消。

某项检查变红时：

| 红色的检查 | 通常原因 | 怎么做 |
| --- | --- | --- |
| Lint and type-check，只有 mypy | 某个 `type: ignore` 在有 PySide6 存根时需要、没有时多余，或反过来 | 让代码在两种环境下都能通过类型检查（声明属性、返回值），而不是忽略；在第二个 venv 里 `pip install -e ".[dev]"` 可以重现 CI 的作业 |
| Lint and type-check，Ruff | 格式 | `ruff format .` |
| Documentation links / CLI examples | 文件移动了，或示例命令解析器不再接受 | 改文档；`check_cli_docs.py` 会指出文件、行和解析器的消息 |
| 只有某个操作系统上的 Tests 红 | 路径、编码或换行假设 | 作业日志指出测试名；用 `PYTHONIOENCODING=cp1252` 或单元测试里的 Windows 路径重现，修代码，保留测试 |
| 所有 Tests 红，覆盖率那一行 | 套件通过了，但 `core`/`models` 覆盖率低于 85 % | 为新分支补合成测试；绝不降低门槛 |
| Tests 在所有平台上每个测试都通过，随后进程在解释器退出时崩溃（`QObject: shared QObject was deleted directly`，Linux 退出码 134 / 139，Windows 127） | 新版 PySide6 改变了 Qt 在关闭阶段能容忍的顺序；`gui` extra 正因此设有版本上限（`docs/DEPENDENCIES.md` §4），`tests/conftest.py` 在会话结束时按已知顺序销毁 Qt 对象 | 在 venv 里装上新版 PySide6，用 `tests/ui` 重现（单个模块都能通过，整个目录不能）；先扩展 `tests/conftest.py` 里的会话结束销毁逻辑，再在两条线上放开上限（这是发布工程改动），绝不能靠跳过 GUI 测试 |
| Release 的某个 bundle 作业 | PyInstaller 锁文件、没有许可证文本的原生库、GPL-only 的 Qt 模块 | `requirements/bundle.lock`（`scripts/compile_bundle_lock.py`）、`packaging/licenses/native/`、`packaging/pyinstaller_filters.py`；门槛脚本会指出是哪个文件 |
| Release 的 draft 作业 | 两个草稿、tag 指向另一个提交、手工附加的文件 | `scripts/release_draft.py` 拒绝猜测；删掉多余的草稿或文件后重新运行 |

失败的测试绝不是“偶发”、重跑到绿为止：找到原因。绝不跳过、禁用或删除测试来换取通过。

## 5. 收到报告时

Issue 表单（`.github/ISSUE_TEMPLATE/`，中英文成对）会收集环境报告（`reverbscope doctor --probe --out report.txt`）、版本与构建提交、相关文件和预期结果。然后按顺序（CONTRIBUTING.md 的 “From a community report to a regression test”）：

1. 用附件复现。把文件裁到仍然失败的最小样本，加入回归语料库（`tests/corpus/manifest.json`，由 `tests/corpus/generate.py` 生成），或者写合成测试（`tests/conftest.py` 里有房间和衰减的生成器）。
2. 在报告所在的线上修：候选版的 bug 先修在 `release/0.5.0`，再把同一个提交 merge 或 cherry-pick 到 `main`。CHANGELOG 条目在同一个提交里。
3. 在 issue 中记录结论；只有在真实设备上的运行才在 [HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md) 或 [VALIDATION.md](VALIDATION.md) 里写 PASS / FAIL 行并附 issue 编号。合成结果和 CI 结果永远不填这些表。
4. 如果修复改变了存储的数字或文件字段，遵守 [API_STABILITY.md](API_STABILITY.md)（只做增量改动；读取方必须改时提升 `schema_version`；先弃用再移除）。

## 6. 东西在哪里

| 需要 | 位置 |
| --- | --- |
| 实现了什么、运行过什么、在哪里运行 | [STATUS.md](STATUS.md)（带日期的快照，英文）、`CHANGELOG.md` |
| 每个数字的算法、单位、有效性 | [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md)（英文） |
| 哪些检查需要硬件 | [OFFLINE_CHECKS.md](OFFLINE_CHECKS.md)、[HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md)、[VALIDATION.md](VALIDATION.md) |
| 依赖与许可证 | [DEPENDENCIES.md](DEPENDENCIES.md)、[THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md)、`scripts/build_license_bundle.py` |
| 没有 Actions 分钟时构建发布 | RELEASE_PLAN §3a、`scripts/build_release.py` |
| 耗时与内存 | [PERFORMANCE.md](PERFORMANCE.md)、`scripts/benchmark.py`、`scripts/bench_dsp.py` |
| 翻译 | `src/reverbscope/locale/zh_CN/LC_MESSAGES/reverbscope.po`；`tests/unit/test_i18n_catalog.py` 对任何未翻译的字串、被弃用的中文词（一个概念一个词）和紧挨中文的 ASCII 标点报错；`tests/unit/test_cli_layout.py` 检查整屏输出的标点和换行 |
