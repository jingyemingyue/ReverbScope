# ADR-0001: v1.0 architecture decisions

Status: accepted as the working design (ARCHITECTURE_V1.md §11).

This page records the decisions in the v1.0 architecture so later changes have
a place to update. Context and alternatives live in that document.

| Decision | Chosen |
| --- | --- |
| Desktop toolkit | PySide6 Essentials + matplotlib |
| Bundling | PyInstaller one-directory; unsigned until signing identities exist |
| Plug-in discovery | `importlib.metadata` entry points |
| Internationalisation | stdlib gettext; Babel is an optional `i18n-dev` extra |
| Core diagnostics | English in `result.json`; verbatim in the UI |
| Schemas | Hand-maintained JSON Schema; `jsonschema` in tests only |
| Settings | JSON under `REVERBSCOPE_HOME`, written by package code |
| Project index | `project.json` listing session folders |
| Comparison time origin | Direct sound; electrical zero when both have loopback |
| Loopback compensation | Regularised division inside the excitation band |
| Audio backend | PortAudio behind a protocol; fake backend for CI/Demo |
| Minimum Python | 3.12 |
| Curves | JSON with `--no-curves`; CSV exporter for interop |
