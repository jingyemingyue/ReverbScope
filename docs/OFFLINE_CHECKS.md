# Checks without hardware

Run these checks from the repository root, after the developer install in
[CONTRIBUTING.md](../CONTRIBUTING.md). They use synthetic signals, the fake
backend and the scripted stand-ins already in the tests. No sound card,
microphone, loudspeaker, DAW or lidar is needed. They do not establish a
hardware PASS.

## Automated gates

```bash
QT_QPA_PLATFORM=offscreen pytest --cov=roomscope.core --cov=roomscope.models --cov-fail-under=85 --cov-report=term
ruff check .
ruff format --check .
mypy
python scripts/check_doc_links.py
python scripts/check_cli_docs.py
python scripts/check_src_safety.py
python scripts/build_docs_site.py --out /tmp/roomscope-site
```

`check_cli_docs.py` parses complete `roomscope` commands in `bash`, `sh`,
`shell` and `console` fences in root Markdown files and under `docs/`. It
uses the current CLI parser, including required arguments, types, choices,
global options and nested commands. Quoted paths, comments, `$` prompts and
backslash continuations are supported. Inline prose and text transcripts
are outside this check; shell pipelines and substitutions are not expanded.
Even examples of real-device commands are **only parsed**, never executed.
A stale example reports its document, line, command and parser diagnostic.
Missing scan directories and empty scans fail instead of reporting success.

The GUI tests run offscreen and may report an explicit skip when an optional
Qt module or a Chinese font is unavailable. Report those skips with the
results. They are not evidence of a working desktop on a physical machine.

## Reproducible CLI workflow

Use a fresh working directory for these output names. Keep an isolated
`ROOMSCOPE_HOME` if you want the run's settings, logs and recent sessions
separate from your usual data. All measurements below are simulated. The
`--backend fake` option belongs **before** the command; the global
`--format json` belongs there too. `export --format csv` selects an exporter.

```bash
roomscope --backend fake --format json devices --probe
roomscope --backend fake --format json doctor --probe
roomscope demo --out offline-demo
roomscope analyze --recording offline-demo/position-a.wav \
  --sweep offline-demo/sweep.roomscope-sweep.json --out offline-import
roomscope --format json show offline-import --no-curves
roomscope --format json compare offline-demo/position-a offline-demo/position-b \
  --same-input-gain --out offline-comparison.json
roomscope export offline-import --format csv --out offline-csv
roomscope session bundle offline-import --no-audio --out offline-report.zip
roomscope project init --out offline-project --name "Synthetic room"
roomscope project add offline-project offline-demo/position-a --position A
roomscope project add offline-project offline-demo/position-b --position B
roomscope --format json project average offline-project
roomscope --backend fake measure --out offline-take \
  --duration 2 --post-silence 1.5 --level -20
roomscope --format json show offline-take --no-curves
```

[test_offline_cli.py](../tests/integration/test_offline_cli.py) runs these
exact commands in a temporary directory, refuses any real audio backend,
checks JSON output and saved files against the shipped schemas, checks CSV
and ZIP contents, and verifies that importing the synthetic take leaves
the source files unchanged. It tests command wiring and artifact contracts;
it does not add or change measurement algorithms.

For an installed CLI or a release bundle, run
`python scripts/smoke_bundle.py --no-gui --out /tmp/roomscope-smoke-session`.
This also uses fake acquisition and checks the demo and JSON output.
`--no-gui` skips the offscreen GUI launch and allows the optional Qt packages
to be absent in a CLI-only source or wheel install; a frozen Terminal Edition uses
`--terminal` to check its library exclusions and GUI refusal as well.
Each smoke subprocess has a timeout. A failure names the command and exit
code, or the timeout/start error, and retains captured stdout and stderr.
Malformed JSON and malformed doctor metadata fail with a readable reason.
The smoke uses its own RoomScope home and UTF-8 for both child pipes and
its own stdout/stderr, including redirected Windows logs that otherwise
use cp1252. Developer settings cannot change the run. None of these
results validate a physical driver or interface.

## Evidence that still needs hardware

Leave [HARDWARE_TESTS.md](HARDWARE_TESTS.md) unchanged for an offline-only
run. Before claiming physical-interface support, its matrix still needs
dated reports for device enumeration, 44.1/48/96 kHz negotiation, channels
beyond 1–2, electrical loopback, Stop during playback, under/overflow
behaviour, unplugging during a take and a full Standalone measurement.
Actual DAW playback, recording and export still need the DAW matrix runs;
synthetic file-format tests cannot validate DAW menus or driver routing.

The real-room/reference-instrument and tape-measure campaign in
[VALIDATION.md](VALIDATION.md) also remains pending. This workflow gives no
evidence for lidar connectivity, point clouds or spectral-measurement
hardware. Existing [recording fixtures](../tests/fixtures/README.md) contain
no real recordings at present; generated signals are not replacements for
the campaign evidence.

In a pull request, record the tested commit, platform/Python version,
commands, pass/skip/fail results and the hardware checks left unrun. Do not
copy an offline success into the hardware matrix.
