# RoomScope documentation

**English** | [简体中文](index.zh-CN.md)

RoomScope measures a recording room so you can hear what the room is doing
to close-miked sources. This hub is the existing docs site: installation,
the sweep workflow, DAW follow, and the analysis report.

GitHub renders the Markdown. A themed HTML site (S7) is generated from
these files:

```bash
python scripts/build_docs_site.py --out site
```

The generator uses only the standard library. Open `site/index.html`.
Each page gets a title, a description, a canonical URL, and Open Graph
title/description. The build also writes `site/sitemap.xml` and
`site/robots.txt` (crawlers are allowed). The repo has **no public docs
host yet**; canonical URLs use the placeholder
`https://docs.example.invalid/roomscope/` until you pass
`--base-url https://your.host/path/`. Copy the `site/` folder to any
static host. This repository does not submit the site to Google, buy a
domain, or enable a host account.

## Languages / 语言

User documents are in English and Simplified Chinese (简体中文). The English
text is authoritative; each Chinese page links back to it. Developer and
internal documents (architecture, ADRs, research notes, dependency and
licence reviews, code provenance, status, release plan) are English-only;
the release plan and the v1.0 architecture have a Chinese digest.
用户文档提供英文和简体中文两种版本，以英文版为准；开发者与内部文档只提供英文版。

| Document / 文档 | English | 简体中文 |
| --- | --- | --- |
| Project overview / 项目简介 | [README.md](https://github.com/jingyemingyue/RoomScope/blob/main/README.md) | [README.zh-CN.md](https://github.com/jingyemingyue/RoomScope/blob/main/README.zh-CN.md) |
| Installation / 安装 | [INSTALLATION.md](INSTALLATION.md) | [INSTALLATION.zh-CN.md](INSTALLATION.zh-CN.md) |
| User guide / 用户指南 | [user-guide/en.md](user-guide/en.md) | [user-guide/zh-CN.md](user-guide/zh-CN.md) |
| Measuring through your DAW / 用 DAW 测量 | [user-guide/daw-setup.md](user-guide/daw-setup.md) | [user-guide/daw-setup.zh-CN.md](user-guide/daw-setup.zh-CN.md) |
| Compatibility / 兼容性 | [COMPATIBILITY.md](COMPATIBILITY.md) | [COMPATIBILITY.zh-CN.md](COMPATIBILITY.zh-CN.md) |
| Editions: Desktop, Terminal, developer tools / 桌面版、终端版与开发者工具 | [EDITIONS.md](EDITIONS.md) | [EDITIONS.zh-CN.md](EDITIONS.zh-CN.md) |
| How RoomScope compares / 与同类工具的比较 | [COMPARISON.md](COMPARISON.md) | [COMPARISON.zh-CN.md](COMPARISON.zh-CN.md) |
| Audio devices and host APIs / 音频设备与主机 API | [AUDIO_DEVICES.md](AUDIO_DEVICES.md) | [AUDIO_DEVICES.zh-CN.md](AUDIO_DEVICES.zh-CN.md) |
| Hardware test matrix / 硬件测试矩阵 | [HARDWARE_TESTS.md](HARDWARE_TESTS.md) | [HARDWARE_TESTS.zh-CN.md](HARDWARE_TESTS.zh-CN.md) |
| Security policy / 安全策略 | [SECURITY.md](https://github.com/jingyemingyue/RoomScope/blob/main/SECURITY.md) | [SECURITY.zh-CN.md](https://github.com/jingyemingyue/RoomScope/blob/main/SECURITY.zh-CN.md) |
| Contributing / 贡献指南 | [CONTRIBUTING.md](https://github.com/jingyemingyue/RoomScope/blob/main/CONTRIBUTING.md) | English only; issues in Chinese are welcome / 仅英文，欢迎用中文提 issue |
| Validation campaign protocol / 验证方案 | [VALIDATION.md](VALIDATION.md) | English only / 仅英文 |
| Measurement methodology / 测量方法 | [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) | English only / 仅英文 |
| Changelog / 更新日志 | [CHANGELOG.md](https://github.com/jingyemingyue/RoomScope/blob/main/CHANGELOG.md) | English only / 仅英文 |

## For users

- **[Download and install](INSTALLATION.md)** · [下载与安装](INSTALLATION.zh-CN.md)
- [User guide (English)](user-guide/en.md)
- [用户指南（中文）](user-guide/zh-CN.md)
- [Measuring through your DAW](user-guide/daw-setup.md) · [用 DAW 测量](user-guide/daw-setup.zh-CN.md)
- [How RoomScope compares](COMPARISON.md) · [与其他工具的比较](COMPARISON.zh-CN.md)
- [Audio devices and host APIs](AUDIO_DEVICES.md) · [音频设备与主机 API](AUDIO_DEVICES.zh-CN.md)
- [Desktop and Terminal Editions, developer tools](EDITIONS.md) · [桌面版、终端版与开发者工具](EDITIONS.zh-CN.md)
- [Compatibility review](COMPATIBILITY.md) · [兼容性](COMPATIBILITY.zh-CN.md)
- [Validation campaign protocol](VALIDATION.md)
- [Hardware test matrix](HARDWARE_TESTS.md) · [硬件测试矩阵](HARDWARE_TESTS.zh-CN.md)
- [文档索引（中文）](index.zh-CN.md)

## For developers

- [Release plan](RELEASE_PLAN.md)
- [Release plan (中文摘要)](RELEASE_PLAN.zh-CN.md)
- [Architecture (v0.1)](ARCHITECTURE.md)
- [Architecture v1.0](ARCHITECTURE_V1.md)
- [Architecture v1.0 (中文摘要)](ARCHITECTURE_V1.zh-CN.md)
- [Measurement methodology](MEASUREMENT_METHODOLOGY.md)
- [Status](STATUS.md)
- [ADR 0001 — v1 architecture decisions](adr/0001-v1-architecture-decisions.md)
- [Project brief (中文)](PROJECT_BRIEF.zh-CN.md)

## Licence and provenance

- [Dependencies](DEPENDENCIES.md)
- [License decision](LICENSE_DECISION.md)
- [Third-party review](THIRD_PARTY_REVIEW.md)
- [Code provenance](CODE_PROVENANCE.md)

## Research notes

- [Literature](research/literature.md)
- [Reference repositories](research/reference_repos.md)
- [Dependency research](research/dependencies.md)
