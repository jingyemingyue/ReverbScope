# Performance and memory

> 中文用户：本文记录分析链的耗时与内存及其测量方法，只提供英文版。

What a user waits for, measured on synthetic recordings with
`scripts/benchmark.py`, and what the numbers taught us. One run on one
machine says nothing absolute: compare runs on the same machine, before and
after a change. The script never touches a real room.

## How to measure

```bash
python scripts/benchmark.py            # five cases, a few minutes
python scripts/benchmark.py --quick    # 2 s and 10 s at 48 kHz
python scripts/benchmark.py --gui      # also the Results page's plots (Agg)
python scripts/benchmark.py --json     # for a spreadsheet or a diff
```

Each case builds a synthetic room (`reverbscope.audio.fake.make_rir`), the
recording of a sweep in it, and then times `analyze`, the interpretation,
the text report, `save_measurement`, `load_measurement`, `compare` and the
five plots. Peak memory is `tracemalloc`'s peak over a run of its own,
because tracing slows allocation-heavy code several times over and would
inflate the timings. Timings are wall-clock, one run; the second case of a
run benefits from caches the first one filled (see below), which is what
happens in the desktop app too.

## Reference numbers

Linux container, Python 3.13, NumPy 2.5, SciPy 1.18, x86_64, 2026-10-07,
after the changes listed below. A sweep of *d* seconds is analysed from a
recording of *d* + 3 s (1 s before, 2 s after).

| Sweep | Rate | `analyze` | Peak memory | Save | Load | Report | Compare | Plots | `result.json` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 s | 48 kHz | 0.70 s | 27 MiB | 0.18 s | 0.13 s | 10 ms | 31 ms | 0.74 s | 4.6 MiB |
| 10 s | 48 kHz | 0.48 s | 47 MiB | 0.17 s | 0.13 s | 9 ms | 31 ms | 0.44 s | 4.6 MiB |
| 60 s | 48 kHz | 3.3 s | 266 MiB | 0.20 s | 0.12 s | 8 ms | 28 ms | 0.43 s | 4.6 MiB |
| 10 s | 96 kHz | 2.3 s | 93 MiB | 0.34 s | 0.23 s | 10 ms | 58 ms | 0.51 s | 9.4 MiB |
| 60 s | 96 kHz | 7.3 s | 532 MiB | 0.44 s | 0.33 s | 10 ms | 66 ms | 0.49 s | 9.5 MiB |

The 2 s case is slower than the 10 s case because it ran first and filled
the filter cache (below); the first plot of a run pays matplotlib's font
set-up.

## What dominates, and what was done

* **The noise floor's octave-band filters** (`core/noise.py`, `_band_levels`)
  cost 0.4 s of a 1.0 s analysis at 48 kHz: for every band,
  `filters.settling_samples` filtered a 4 s impulse to find the length of
  the filter's start transient. The length is a function of the filter and
  the rate alone, so it is now cached per process (`filters._SETTLING`); a
  comparison, a project overview or the desktop app's second analysis skips
  it. The numbers are unchanged: a cached value is the value that would be
  computed.
* **Loading a session** spent 0.3 of 0.38 s in the JSON nesting guard
  (`jsonutil.json_nesting_depth`), a Python loop over every character of a
  result.json of several megabytes. It now scans with a regular expression
  that skips strings whole and visits only brackets; a test keeps it equal
  to the loop on escaped quotes, brackets inside strings and unterminated
  strings.
* **The frequency response** is 89 % of `result.json`: three arrays of
  131072 points at 48 kHz (262144 at 96 kHz), 4.6 MiB and 9.4 MiB of text.
  It is also what the Results page draws. Storing it on a log-spaced grid of
  a few thousand points would cut the file, the save, the load and the plot
  by most of that, at the price of a different (coarser) stored curve for new
  sessions; it is a documented option, not done, because the stored curve is
  Tier 1 data and the change deserves its own review
  (`docs/API_STABILITY.md`).
* **Peak memory** is the FFT work on arrays as long as the recording: at
  60 s and 96 kHz (6.1 million samples, 47 MiB as float64) the peak is
  532 MiB, reached while `_ideal_pulse` convolves the sweep with its inverse
  filter (`fftconvolve` holds two complex spectra and the full output while
  the located impulse response, the recording and the inverse filter are
  alive). At 48 kHz and 10 s, the common case, the peak is 47 MiB. An
  overlap-add convolution would bound the transient at the cost of
  last-bit differences in the pulse; not done for the same reason as above.
* **Saving** writes `result.json` with indentation and `fsync`s every file
  so a crash never leaves half a session; the JSON encoding of the response
  arrays is most of the 0.2–0.4 s.
* **Everything else** is fast: the interpretation, health, verdicts and the
  text report take milliseconds; `compare` tens of milliseconds; the five
  plots under half a second.

## Attributing memory

`tracemalloc.get_traced_memory()` sampled from a thread while `analyze`
runs, with the pipeline's stage functions wrapped to record which one is
active, attributes the peak to a stage (this is how the `_ideal_pulse`
figure above was found). It is a diagnostic, not part of the script: the
wrapping changes nothing in the numbers but is not something to ship.
