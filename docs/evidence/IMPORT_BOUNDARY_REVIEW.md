# Imported-data boundary review

This record follows GUIDELINES.zh-CN.md §4 C5/C12/C16 and §6, with the
repository's SECURITY.md as its security policy. Evidence: offline source
review and small synthetic regressions. This is not an official Codex
Security scan or an exhaustive repository audit; that capability was not
available in this session.

## Confirmed issues and corrections

| Boundary | Before | Correction and regression |
| --- | --- | --- |
| Audio import | `read_wav` decoded all frames without an allocation budget. Encoded size does not bound losslessly decoded float64 data. A 627-byte synthetic FLAC decoded to 1,600,000 bytes. | Preflight frame/channel counts; accept at most 512 MiB in one decoded array; bound the actual frame read and check its result. Tests use small budgets with WAV, FLAC, stereo and understated metadata. |
| JSON import | A stat size check was followed by an unbounded text read. A file growing after stat could bypass the configured size cap. | Read at most `max_bytes + 1` bytes, check the actual count, then decode UTF-8 with BOM support. The deterministic growth regression preserves the existing cap. |
| Diagnostics | A skipped bundle member's untrusted name reached configured logging handlers with raw terminal controls and line breaks. | Escape message controls using the existing CLI sanitizer, indent exception/stack blocks, and operate on a copied LogRecord. Tests preserve readable tracebacks and the original record for other handlers. |

Six initial regressions failed before the corrections. An additional
sentinel test verifies the actual bounded audio read when metadata
understates the returned data. All seven are in
[test_import_boundaries.py](../../tests/robustness/test_import_boundaries.py).

The bundle-to-log reproduction used only a temporary benign outside file.
Before the fix, its link name produced a literal escape and two output
lines; after the fix, no literal escape and one line. The archive contained
only session.json in both cases: its existing outside-link exclusion was
preserved.

## Scope and limits

Review focused on the audio/JSON readers, session member resolution and
bundling, atomic writes, project references, scan read limits, and configured
diagnostic handlers. The existing scan reader already checks growth while
reading; session paths and bundle members already reject outside links.
External project session references are allowed by SECURITY.md and were
not reported as a vulnerability.

The audio limit concerns the accepted decoded array, not total process,
codec or subsequent DSP memory; an over-budget sentinel may read one extra
frame. The JSON growth case requires a concurrently mutable file. Neither
finding establishes code execution. Native-codec internals, operating-system
races, arbitrary third-party handlers, real devices and DAWs were not audited.
No dependency, data format, audio backend or measurement algorithm changes
are included in this fix.
