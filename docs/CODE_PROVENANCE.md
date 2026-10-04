# Code provenance

Last reviewed: 2026-09-24 (v0.4.1; re-checked for the files that release changes —
no third-party source was added).

Additional review: 2026-10-04 for the optional local decay fitter and its
synthetic-trained model. No third-party source, weights or training data
were added; the scope and pinned conceptual references are recorded below.

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

The optional local decay fitter and its 64-input, 32-hidden-unit,
5-output model (2,245 weights and biases) are independently implemented.
Training uses only the project's own analytic synthetic block-power curves
and Gaussian noise. The packaged JSON weights are produced by that local
training procedure, not copied from DecayFitNet or another model. No
external dataset or unknown pretrained weight file is used. The runtime
records the artifact's SHA-256, identity and parameter count.

The reviewed artifact is
`src/roomscope/model_data/decay_initializer_v1.json`, model
`roomscope-decay-initializer-v1`, 51,257 bytes, SHA-256
`2ba0004247ce90ff70e92fb0e97ae14f59d12d92e6029732224c853fecc12234`.
Its own training metadata records 12,000 generated examples, 120 epochs,
seed `20261004` and a distinct 1,000-example evaluation seed `20261005`.
The weights and synthetic generator are Apache-2.0 project material.
Raw initializer errors and final physical-fit benchmark results are kept
separate in LOCAL_DECAY_MODEL.md; the benchmark shows no demonstrated
accuracy or speed advantage from the neural seed.

Götz et al. (2022), *Neural network for multi-exponential sound energy
decay analysis*, DOI [10.1121/10.0013416](https://doi.org/10.1121/10.0013416),
is a conceptual reference for synthetic training and exponential decay
parameter estimation. DecayFitNet's README and MIT LICENSE were inspected
at commit `01daf3e7bbfd637aa1269bbca0cab7f445db0d5d`; no implementation
source or network weights were read or imported. Its finite-window
Schroeder-integrated EDF model and approximately 677,000-parameter network
are not the model used here: RoomScope fits exact block averages of raw
power with a stationary floor, then uses a constrained physical optimizer
to refine initial values. Repository documentation from pyrato and
pyroomacoustics was also reviewed as recorded in THIRD_PARTY_REVIEW.md,
without source adoption. Details and limits are in
[LOCAL_DECAY_MODEL.md](LOCAL_DECAY_MODEL.md).

## How to update this file

When adapting or copying third-party code becomes necessary:

1. Complete the license check in THIRD_PARTY_REVIEW.md first.
2. Add a row above with every column filled (no "unknown").
3. Keep the upstream copyright and license notice in the local file.
4. Add the notice to `NOTICE` if the upstream license requires it
   (Apache-2.0 NOTICE files, BSD advertising clauses, etc.).
