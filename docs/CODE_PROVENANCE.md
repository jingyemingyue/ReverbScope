# Code provenance

Last reviewed: 2026-10-03 (referenced device parameters added to
`src/roomscope/audio/referenced.py`; Chu noise-power subtraction added to
`core/decay.py` from the published method; no third-party source was copied).

## Vendored or adapted third-party source files

**No third-party source files currently vendored.**

No file in `src/`, `tests/`, `examples/` or `scripts/` was copied or adapted
from another repository, gist, blog post, Q&A site or AI answer of unknown
origin. All DSP is implemented from the published equations and step
descriptions cited in MEASUREMENT_METHODOLOGY.md.

The table below is empty by design and must be filled in before any
third-party code enters the tree:

| local file | upstream file | upstream project | upstream URL | commit hash | copyright holder | license | modification description |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (none) | | | | | | | |

## Third-party *libraries* (used, not copied)

RoomScope imports NumPy, SciPy, soundfile, sounddevice, matplotlib and
(optionally) PySide6 as ordinary dependencies. Their licenses, bundled native
libraries and redistribution obligations are recorded in DEPENDENCIES.md.
Using a library through its public API is not vendoring and creates no
entry above.

## Verbatim texts that are *not* code

| file | source | reason |
| --- | --- | --- |
| `LICENSE` | https://www.apache.org/licenses/LICENSE-2.0.txt (SHA-256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30) | the license text itself, reproduced verbatim as required |
| `docs/PROJECT_BRIEF.zh-CN.md` | project owner's brief | project's own material |
| `packaging/licenses/GPL-3.0.txt` | https://www.gnu.org/licenses/gpl-3.0.txt (SHA-256 3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986) | GPL-3.0 text shipped in desktop bundles (Qt / PySide6 notices, DEPENDENCIES.md §3) |
| `packaging/licenses/LGPL-3.0.txt` | https://www.gnu.org/licenses/lgpl-3.0.txt (SHA-256 e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118) | LGPL-3.0 text shipped in desktop bundles (PySide6 Essentials / Qt) |
| `packaging/licenses/PortAudio-LICENSE.txt` | header block of https://github.com/PortAudio/portaudio/blob/master/LICENSE.txt, comment markers removed (SHA-256 of the file: 010ca829908cc697aeb7d18f5ed4e94c3f031ab5cd78e213b9cb4545244aae00) | PortAudio notice for the library bundled by sounddevice |

## Referenced device parameters (not code)

`src/roomscope/audio/referenced.py` stores published numbers (channel
counts, sample rates, compiled latencies) read from public documents and
open-source files already cited in AUDIO_DEVICES.md. **No third-party
source was copied.** Each value has a URL and locator. These are not
RoomScope hardware results.

| local field | source | URL / locator |
| --- | --- | --- |
| WASAPI 10 ms | Microsoft Learn, Low Latency Audio | https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/low-latency-audio |
| MME 90 / 180 ms | PortAudio v19.7.0 `pa_win_wmme.c` | `PA_MME_WIN_WDM_DEFAULT_LATENCY_ (0.090)`; high = 2× |
| DirectSound 120 / 240 ms | PortAudio v19.7.0 `pa_win_ds.c` | `PA_DS_WIN_WDM_DEFAULT_LATENCY_ (.120)`; high = 2× |
| WDM-KS 10 / 40 ms | PortAudio v19.7.0 `pa_win_wdmks.c` | `Type_kWaveRT` defaults |
| ALSA 8 / 32 ms @ 48 kHz | PortAudio v19.7.0 `pa_linux_alsa.c` | `GropeDevice` 512/128 and 2048/512 |
| OSS 8 / 32 ms @ 48 kHz | PortAudio v19.7.0 `pa_unix_oss.c` | 4 fragments × 128 frames |
| Core Audio fallback 10 / 100 ms | PortAudio v19.7.0 `pa_mac_core.c` | fallback when device latency is unreadable |
| ALSA dmix 48 kHz / 2 ch | alsa-lib v1.2.13 `src/conf/alsa.conf` | `defaults.pcm.dmix.rate` / `.channels` |
| PipeWire graph 48 kHz | pipewire.conf(5) | `default.clock.rate = 48000` |
| Scarlett 2i2 4th Gen 2/2, 44.1–192 kHz, 24-bit | Focusrite specifications | https://userguides.focusrite.com/hc/en-gb/articles/19640392541202-2i2-4th-Gen-Specifications |
| Scarlett 18i20 4th Gen 8 analog in | Focusrite user guide | https://userguides.focusrite.com/hc/en-gb/articles/21616163352722-Using-your-18i20-4th-Gen |
| Babyface Pro FS 4/4, 28–200 kHz | RME product page | https://rme-audio.de/babyface-pro-fs.html |

PortAudio is already a dependency via python-sounddevice (THIRD_PARTY_REVIEW.md,
MIT). Manufacturer pages are documentation, not source code.

## Conceptual references only

The repositories listed in THIRD_PARTY_REVIEW.md were studied for feature
design and algorithm names only. In particular, no code was taken from the
GPL projects DRC and Aliki, from the proprietary Room EQ Wizard, or from the
unlicensed gists and course projects that surfaced in searches.

The loopback compensation in `core/loopback.py` (regularised spectral
division with the peak of the interface FIR as time origin, the settling and
late-peak checks) was implemented clean-room from the published
regularised-inversion formula of Kirkeby et al. (1998) as Farina (2007)
states it, and from Müller & Massarani (2001), cited in
MEASUREMENT_METHODOLOGY.md §2a (reference [22] records that Kirkeby's own
text was not re-read); no measurement program's source was consulted.

The image-source mathematics in `core/placement.py` (and the synthetic
arrivals its tests are built from) was implemented clean-room from the
published relation in Allen & Berkley (1979); no code was taken from
pyroomacoustics (MIT, EPFL-LCAV), which THIRD_PARTY_REVIEW.md records as
evaluated and not adopted — adopting it would also bring its Eigen
(MPL-2.0) obligation, see DEPENDENCIES.md. RoomScope does not implement
room-shape-from-echoes / echo sorting (Dokmanić et al., 2013); it is cited in
MEASUREMENT_METHODOLOGY.md §9 as the published method the project declines,
and no implementation of it was consulted.

The Chu noise-power subtraction in `core/decay.py` (subtract the Lundeby
mean-square noise estimate from `h²` before Schroeder integration, clip
negatives to zero, keep Lundeby truncation and late-decay compensation)
was implemented clean-room from Chu (1978) as restated by Karjalainen et
al. (2002) and compared by Guski & Vorländer (2014), cited in
MEASUREMENT_METHODOLOGY.md §3 [25]. pyrato's documented
`energy_decay_curve_chu_lundeby` (https://pyrato.readthedocs.io/en/latest/modules/pyrato.edc.html)
was the conceptual prompt for combining the two published steps; **no
pyrato source was read or copied.**

## How to update this file

When adapting or copying third-party code becomes necessary:

1. Complete the license check in THIRD_PARTY_REVIEW.md first.
2. Add a row above with every column filled (no "unknown").
3. Keep the upstream copyright and license notice in the local file.
4. Add the notice to `NOTICE` if the upstream license requires it
   (Apache-2.0 NOTICE files, BSD advertising clauses, etc.).
