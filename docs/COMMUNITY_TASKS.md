# Contributor task backlog

These are **proposed tasks**, not fabricated issues, users or completed tests.
Before claiming one, check [open issues](https://github.com/jingyemingyue/ReverbScope/issues)
and [PRs](https://github.com/jingyemingyue/ReverbScope/pulls), then open a real
report/proposal describing the equipment or work you can supply. Maintainers
apply labels after confirming scope. Chinese reports are welcome; the full
[Chinese test guide](COMMUNITY_TESTING.zh-CN.md) covers the same workflow.

| Suggested label | Concrete task | Acceptance / evidence |
| --- | --- | --- |
| good first issue | Check one Fender Studio Pro / Studio One guide subsection against your installed version | Exact app version/language, actual import/Tempo/export labels, reviewed screenshots, small bilingual doc correction if needed; compatibility stays NOT RUN without a physical capture |
| good first issue | Verify public beta first launch on an Intel Mac or macOS 14 machine | Download exact asset, verify checksum, record native OS/CPU/app version and silent demo outcome; install failure is useful, no interface needed, hardware rows stay NOT RUN |
| good first issue | Improve one unclear step after actually following the public install guide | File/step, expected/actual outcome, proposed English/Chinese wording and successful doc-link check; avoid changing unrelated GUI labels |
| help wanted | First independent Apple Silicon interface test | Execute the short guide, attach environment/hash/routing and per-row outcomes; unsupported rates or no loopback cable remain NOT RUN |
| help wanted | Windows WASAPI physical test | Full take, actual Windows Default Format and rate, Stop, buffer/latency log; report ASIO-only restrictions honestly, no unsupported compatibility claim |
| help wanted | One real Pro Tools, Logic or REAPER roundtrip | Mic recording, clean export, sweep sidecar, result/validity, exact DAW version and follow-up report |
| help wanted | Propose hash-pinned build tooling without changing release policy | Inventory build inputs not fixed by the runtime lock, narrow implementation plan and reproducibility experiment; review before adding dependencies/workflow cost |

No issue is created merely to increase activity. Useful failures go through
[CONTRIBUTING](../CONTRIBUTING.md): reproduce, minimize non-private input, add a
regression, fix, retest with the reporter and then update the evidence matrix.
These tasks do not require stars, testimonials, purchase of gear or API spending.
