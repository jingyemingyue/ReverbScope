# API and schema stability

> 中文用户：本文面向集成者和贡献者，只提供英文版；用户指南有中文版。

What an integrator or a script may rely on, what may change, and what a
change to a stable surface has to carry with it. The tiers themselves are
defined in [ARCHITECTURE_V1.md §5.1](ARCHITECTURE_V1.md#51-public-api-and-stability-tiers);
this page is the reasoning behind them and the checklist.

## The surfaces

| Surface | Tier | Examples |
| --- | --- | --- |
| The names `reverbscope` exports (`reverbscope/__init__.py`) | 1 | `analyze`, `AnalysisResult`, `compare`, `assess`, `judge_comparison` |
| The files and their schemas (`reverbscope schema <name>`) | 1 | `result.json`, `session.json`, `comparison.json`, `project.json`, the sweep sidecar |
| `reverbscope <command> --format json` payloads | 1 | `show`, `compare`, `project overview`, `profiles`, `doctor`, `devices`, `config` |
| CLI exit codes | 1 | 0 done, 1 error, 2 usage, 130 interrupted |
| Documented module functions and extension points | 2 | `reverbscope.core.*` named in the methodology, `AudioBackend`, `ProfileBase`, `summarize_project`, entry-point groups |
| Everything else | 3 | `reverbscope.ui`, `reverbscope.cli` internals, text reports, help wording, the menu, box glyphs |

Text output is never an interface: a report's wording, its layout (ruled or
boxed), the help screens and the menu are localised and may change in any
release. A script that reads ReverbScope's output uses `--format json`.

## The principles

1. **Additive by default.** A new key, a new optional field, a new member of
   a word list (a validity, a health status, a verdict), a new command or
   option and a new finding topic are additions: they never bump a
   `schema_version` and never need a major release. Readers tolerate what
   they do not know (unknown keys are dropped and logged at INFO); writers
   never emit a key the schema does not list.
2. **Meaning is the contract.** A key's unit, reference, sign, time origin
   and the sense of its validity never change under the same name. A number
   that has to mean something else gets a new key; the old key stays, or
   goes with a `schema_version` bump and a migration.
3. **`schema_version` bumps only for a misreading.** A reader of the
   previous version would get a wrong number, unit or time origin: bump,
   register the migration for lower versions, refuse higher versions with
   the ReverbScope version that can read them named, and keep a sample of
   the old file in `tests/corpus/`. Nothing else bumps it; every file written
   so far is schema 1.
4. **Validity before value.** A metric that cannot be computed is withheld
   with a validity and a reason, never written as 0 or as a guess. Consumers
   read the validity before the number; a value may be `null` wherever a
   validity other than `valid` is possible.
5. **Derived at display time.** Findings, measurement health, verdicts, the
   project overview and the fit of a take are computed when shown and are
   not stored in files (`analysis_summary` in `session.json` is the one
   exception, a courtesy for listings). Their wording, thresholds and rules
   may change between minor releases; the numbers they rest on are in
   `evidence`, `thresholds` and `params`, and a finding carries a stable
   `message_id`. A stored number never changes because an interpretation
   did.
6. **English in files, the interface language on screen.** Every sentence
   stored in a file (`notes`, `warnings`, `reason`) is English, written
   through `diag`; it is translated when displayed. A localised payload
   (`findings`, `health`, `verdict`, `overview`) says its language in
   `locale`.
7. **Deprecation before removal.** A Tier 1 name, key or option that is to go
   keeps working for one minor release with a `DeprecationWarning` (or a
   note under the command, as `--json` had when `--format json` arrived), is
   listed in `CHANGELOG.md`, and is removed only in a major release.
8. **A major release is rare.** Removing or renaming a key or an export,
   changing a unit, a time origin or the sense of a validity, changing an
   exit code: each is a major version. Everything in this document is
   designed so that these do not happen by accident.

## Adding something to a stable surface

A change that touches a Tier 1 surface carries all of this in the same pull
request:

1. The dataclass field with a default, so older files still load, and its
   `to_dict` / `from_dict` (the lenient loader in `models/loadutil.py`).
2. The JSON Schema in `src/reverbscope/schemas/`; the round-trip test proves
   the dataclass validates against it.
3. A line in `ARCHITECTURE_V1.md` §5.2's table when a file gains content, and
   the methodology when a number gains a definition (its algorithm source,
   unit and validity conditions).
4. A corpus sample (`tests/corpus/`) when the loader learned a new shape, and
   a test that an older file without the key still loads.
5. The Tier 1 list in `ARCHITECTURE_V1.md` and `reverbscope/__init__.py`
   when a name is exported (a test keeps them equal).
6. `CHANGELOG.md`, under *Added* or *Changed*, naming the key or name.

A Tier 2 change needs 3 and 6; a signature may gain keyword parameters with
defaults and nothing else. A Tier 3 change needs a test.

## What a consumer can count on

* `result.json` written by any 0.5 or later release loads in every later
  release of the 1.x line, with the same numbers under the same keys.
* `reverbscope --format json <command>` is one JSON document on stdout and
  nothing else; progress, warnings and errors go to stderr.
* A key that is missing, `null` or marked with a validity other than
  `valid` carries no number to use; the `reason` says why.
* A new release may add keys anywhere; a consumer that fails on an unknown
  key is wrong, not the file.
