# Regression corpus

Files that once broke ReverbScope, or that stand for a way a file can be
broken, each with the reason it exists and what must happen when ReverbScope
reads it. `test_corpus.py` runs every entry of `manifest.json` on every CI
run; a file nobody can explain is not allowed in (the test fails on an
unlisted file).

What is here is synthetic: WAV headers assembled by hand with each field
wrong in turn, the containers DAWs export (AIFF, CAF, FLAC, Wave64, RF64)
holding 100 samples of a tone, sweep sidecars re-saved badly, a session saved
by 0.5.0b2 and every way its JSON can be stale, cut off, mis-encoded or
crafted. `generate.py` rebuilds all of it; the manifest is written by hand.

## Rules

* **Small.** A sample is the smallest file that still shows the behaviour:
  a header with 100 frames, a JSON with the one field. The test refuses any
  entry over 64 KB.
* **Synthetic, or minimised and donated.** No real recording longer than a
  second, nothing from another person's machine without their word, no home
  folder, account or device name inside the file. A donated sample is CC0 by
  its contributor, who says so in the pull request.
* **One reason each.** The manifest entry says what the file is for, how it is
  read (`loader`: `wav`, `sidecar`, `session`, `project`, `comparison`) and what
  must happen (`expect`: `loads` with `checks`, or `refused` with the error
  class and a `match`). A fixture from a report names its issue in the reason.
* **Sessions are folders.** A session entry is the folder with `session.json`,
  `result.json` and `impulse_response.wav`; the response is cut to 300
  samples (the loader needs the direct sound only), which keeps every variant
  under 40 KB.

## From a community report to an entry

The loop is in `CONTRIBUTING.md` ("From a community report to a regression
test"). In short: reproduce, cut the file down until it is minimal and holds
nothing personal, drop it under `files/<family>/`, add the manifest entry
with the issue number, write the test so it fails before the fix, fix, and
let the reporter re-verify.
