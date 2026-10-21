# How ReverbScope uses AI

以 [GUIDELINES.zh-CN.md](GUIDELINES.zh-CN.md) 为准。This page says how AI
assistance is allowed to be used. It does not decide product behaviour. The
English summary of the execution standard is
[GUIDELINES.md](GUIDELINES.md). The step-by-step protocol is Appendix J of
the Chinese text, and its working copy is `AGENTS.md`.

The guidelines dated 2026-10-15 record that the project has been advanced
with Claude, Codex, Cursor, Grok, and GPT. That sentence is a citation of
the guidelines, not a fresh count of tools or of pull requests.

## What an AI session may prepare

- A draft a person can review: a small code change, a test, a document, a
  triage note, a comment the maintainer might post.
- One task from §5 of the guidelines, on one branch, as one pull request.
  The description names the section and the task.
- A refresh of an evidence snapshot, with only figures checked that day, and
  a draft of the application texts in Appendix I. Each draft stays at or
  under 500 characters.

## What only the maintainer does

These stay human even when an AI session prepared the change (constraint
C18 and §2.6):

- Merge a pull request. Nothing merges automatically.
- Publish a release, or push a tag. Exception: a small patch release or a
  regular update release that the maintainer explicitly asks for in the
  session (see Releases in `AGENTS.md`).
- Close a pull request.
- Accept a result on real hardware or in a DAW.
- Submit the Codex for Open Source application, after reading the programme
  terms.
- Fill in Appendix F, and decide a conflict the guidelines do not settle.

## How a session stays reviewable

Claim the task before starting: the session or tool, the task, and when it
expects to finish. Forty-eight hours with no progress releases the claim.
Do not push onto someone else's branch. Do not open a second full GUI
redesign; the only GUI integration branch is `gui/redesign`.

At the end, the pull request carries the handoff from Appendix J: what
changed, what did not, which checks ran, the evidence level, and the next
step.

## Evidence

Use the levels in constraint C16, and name the level whenever something is
called tested:

1. A real interface or a real DAW.
2. Automated: CI, the fake audio backend, an offscreen screenshot.
3. A synthetic demo.

An unrun check is written "not run". The maintainer's own activity, an AI
session, CI, and downloads of a draft asset are not users and are not
adoption (decision D19, constraint C15).

## Transparency

A commit message ends with an `Assisted-by:` line naming the tool. The pull
request says which tool was used and whether a maintainer has reviewed it.
Review comes before merge.

## Never

- Buy, trade, or solicit stars, or count them as a goal.
- Put an email address, an OpenAI organization id, a token, or any personal
  detail beyond the public GitHub account into the repository, a commit, a
  pull request, or a comment (constraint C17).
- Force-push, delete a remote branch, rebase a branch that was already
  pushed, or commit on `main`, `release/0.5.0`, or `gui/redesign`.
- Change measurement numbers, file formats, or CLI output as a side effect
  of a GUI or documentation task.
- Add a dependency, an icon, a font, or a palette without the license audit
  in constraint C7.
- Delete a test, skip it, mark it expected-fail, or lower a coverage gate so
  that a change goes green.
- Edit the guidelines, including their version number. A disagreement is a
  guidelines-change proposal in the pull request. Unless the maintainer
  explicitly asks in the session for that edit (see `AGENTS.md`).

## 简体中文

以 [GUIDELINES.zh-CN.md](GUIDELINES.zh-CN.md) 为准。本页只说明项目怎样使用
AI，不另立产品决定。英文摘要是 [GUIDELINES.md](GUIDELINES.md)。逐步做法是
准则附录 J，仓库里的执行版本是 `AGENTS.md`。

准则（2026-10-15）写明，项目曾由 Claude、Codex、Cursor、Grok、GPT 推进。
这句话是引用准则，不是重新统计工具或拉取请求。

### AI 会话可以准备的

- 给人审的草稿：小的代码改动、测试、文档、分诊说明、维护者可能发出的评论。
- 准则 §5 里的一件任务，一个分支，一个拉取请求。描述里写章节号和任务。
- 只含当天核实过的数字的证据快照，以及附录 I 里不超过 500 字符的申请文本草稿。

### 永远由维护者本人做的

即使 AI 准备了改动，下面这些仍然由人来做（硬约束 C18、§2.6）：

- 合并拉取请求。不开自动合并。
- 发布，或推送标签。例外：维护者在会话里明确要求的小补丁版或常规更新版发布（见 `AGENTS.md` 的 Releases）。
- 关闭拉取请求。
- 在真机或 DAW 上验收。
- 阅读条款后，提交 Codex for Open Source 申请。
- 填写附录 F，并裁决准则没有定下的分歧。

### 怎样保持可审

开工前认领：会话或工具、任务、预计完成时间。48 小时没有进展，认领作废。
不往别人的分支上推送。不开第二条整套 GUI 改版；GUI 集成分支只有
`gui/redesign`。

结束时在拉取请求里写附录 J 的交接说明：改了什么、没改什么、跑了哪些检查、
证据级别、下一步。

### 证据

用硬约束 C16 的级别。说“测过”时写明是哪一级：真机或 DAW，然后是自动化
（CI、伪后端、离屏截图），然后是合成演示。没跑的写“未运行”。维护者自己的
活动、AI 会话、CI、草稿资产的下载，都不是用户，也不算采用（决策 D19、
硬约束 C15）。

### 透明

提交信息末尾写 `Assisted-by:`，点明工具。拉取请求写明用了哪个工具、维护者
是否已经审阅。先审后合。

### 禁止

- 买星、互刷、求星，或把星数当成目标。
- 把邮箱、OpenAI 组织 ID、令牌，或公开 GitHub 账号以外的个人资料写进仓库、
  提交、拉取请求或评论（硬约束 C17）。
- 强推、删除远端分支、变基已经推送的分支，或直接提交到 `main`、
  `release/0.5.0`、`gui/redesign`。
- 在 GUI 或文档任务里顺手改变测量数字、文件格式或命令行输出。
- 不按硬约束 C7 做许可证审计就新增依赖、图标、字体或色表。
- 为了让检查变绿而删除测试、跳过测试、标记为预期失败，或调低覆盖率门。
- 修改准则，包括版本号。分歧写成拉取请求里的“准则变更提案”。维护者在会话里明确要求修改时除外（见 `AGENTS.md`）。
