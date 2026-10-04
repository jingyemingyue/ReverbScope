# Third-party repository review

Audit date: 2026-09-17. Every repository that was studied while designing
RoomScope is registered here with the result of its license check. The full
records of the original audit (repository URL, author, commit/tag, verbatim license header,
multiple-license check, file headers, vendored code, NOTICE/COPYRIGHT/AUTHORS
files, patent statements, obligations, and the URL of every fact) are in
[research/reference_repos.md](research/reference_repos.md).
The limited documentation-only review on 2026-10-04 is recorded separately
below; it does not extend the original source-file audit.

**Result: no source code was copied or adapted from any repository.** All of
them were used as *conceptual references* (feature design, algorithm names,
architecture ideas) or as ordinary dependencies. See CODE_PROVENANCE.md.

## Summary

| Project | Repository | License (from LICENSE file) | Copyleft | Affects Apache-2.0? | Classification for RoomScope |
| --- | --- | --- | --- | --- | --- |
| pyroomacoustics | https://github.com/LCAV/pyroomacoustics | MIT | no | no (keep EPFL-LCAV notice if code were copied) | Conceptual reference (ESS/deconvolution API design). Not a dependency. Re-checked 2026-09-21 when image-source mathematics entered `core/placement.py` and its tests: still no code taken, implementation is clean-room from Allen & Berkley (1979). |
| python-acoustics (archived) | https://github.com/python-acoustics/python-acoustics | BSD-3-Clause (template placeholder `{organization}` left in the file) | no | no | Conceptual reference (octave-band and decay API ideas). |
| pyfar | https://github.com/pyfar/pyfar | MIT (bracketed placeholders in the copyright line) | no | no | Conceptual reference (signal/measurement class design). |
| SciPy | https://github.com/scipy/scipy | BSD-3-Clause (+ bundled permissive licenses, none in `scipy.signal`) | no | no | Dependency (public API only). |
| Impulcifer | https://github.com/jaakkopasanen/Impulcifer | MIT | no | no | Conceptual reference (sweep/IR workflow). |
| AutoEq | https://github.com/jaakkopasanen/AutoEq | MIT (measurement data license unclear) | no | no | Conceptual reference only (smoothing ideas). |
| DRC — Digital Room Correction (D. Sbragion) | https://drc-fir.sourceforge.net/ | GPL-2.0-or-later (from docs and SourceForge metadata; tarball not opened) | **yes** | **would force GPL** | Conceptual reference only. No code used. |
| Aliki (F. Adriaensen) | https://kokkinizita.linuxaudio.org/linuxaudio/ | GPL-3.0 (per downloads page; -only vs -or-later UNKNOWN) | **yes** | **would force GPL** | Conceptual reference only. No code used. |
| ITA-Toolbox (RWTH Aachen, MATLAB) | https://git.rwth-aachen.de/ita/toolbox | BSD-4-Clause (advertising clause; GitHub mirror URL does not exist) | no | acknowledgement obligation; GPL-incompatible downstream | Conceptual reference only (Lundeby parameter choices). |
| Room EQ Wizard (REW) | https://www.roomeqwizard.com/ | Proprietary freeware EULA (no source; redistribution and reverse engineering forbidden) | n/a | no code exists to use | Do not use. Feature ideas from public documentation only. |
| acoular | https://github.com/acoular/acoular | BSD-3-Clause | no | no | Conceptual reference only (low relevance). |
| pyrirtool | https://github.com/maj4e/pyrirtool | MIT | no | no | Conceptual reference. |
| phonometry | (GitHub search result, see full record) | MIT | no | no | Conceptual reference. |
| RoomResponse (baranovmv) | (GitHub search result) | MIT | no | no | Conceptual reference. |
| spatialaudio/sweep | https://github.com/spatialaudio/sweep | MIT | no | no | Conceptual reference. |
| Hakim-El/Project_Course_2022 | (GitHub search result) | **none** | unknown | unknown | **License unclear — no source code copied.** |
| pengowray/sweep (JavaScript) | (GitHub search result) | MIT | no | no | Conceptual reference only. |
| ESS gists (akashrajkn; a Farina-formula gist) | GitHub gists | **none** | unknown | unknown | **License unclear — no source code copied.** |
| python-sounddevice (+ examples) | https://github.com/spatialaudio/python-sounddevice | MIT (PortAudio MIT-style; Windows ASIO DLLs carry Steinberg SDK terms) | no | no | Dependency (public API only). |
| python-soundfile | https://github.com/bastibe/python-soundfile | BSD-3-Clause (bundled libsndfile LGPL-2.1+, dynamic) | no | no as a pip dependency | Dependency (public API only). |

## Local decay model: documentation-only review, 2026-10-04

The following versions are conceptual references for the optional local
decay model. Repository metadata, README, LICENSE and the named
documentation were inspected. No source implementation, pretrained weight
file or training dataset was read, copied or imported.

| Project and pinned commit | License and notice in inspected LICENSE | Reviewed material and purpose | Adoption |
| --- | --- | --- | --- |
| [DecayFitNet](https://github.com/georg-goetz/DecayFitNet/tree/01daf3e7bbfd637aa1269bbca0cab7f445db0d5d), `01daf3e7bbfd637aa1269bbca0cab7f445db0d5d` (2023-12-14) | [MIT](https://github.com/georg-goetz/DecayFitNet/blob/01daf3e7bbfd637aa1269bbca0cab7f445db0d5d/LICENSE); copyright 2021 Georg Götz | [README](https://github.com/georg-goetz/DecayFitNet/blob/01daf3e7bbfd637aa1269bbca0cab7f445db0d5d/README.md) and its linked Götz et al. 2022 paper: synthetic training for exponential-decay parameter estimation | Concept only. No original network, source or weights; no dependency. |
| [pyrato](https://github.com/pyfar/pyrato/tree/034c8604d4d94915e72cf9091e790d6c1dd64580), `034c8604d4d94915e72cf9091e790d6c1dd64580` (2026-08-30) | [MIT](https://github.com/pyfar/pyrato/blob/034c8604d4d94915e72cf9091e790d6c1dd64580/LICENSE); copyright 2021–2023 Marco Berzborn / Institute of Technical Acoustics; 2023 the pyfar developers | README and [API reference](https://github.com/pyfar/pyrato/blob/034c8604d4d94915e72cf9091e790d6c1dd64580/docs/api_reference.rst), including documentation headings for `edc`, `parameters` and `parametric`: room-acoustics API organization | Documentation comparison only; no dependency or copied source. |
| [pyroomacoustics](https://github.com/LCAV/pyroomacoustics/tree/ff7d61f219e4eb41489963c4bb5f57bea5bc2c69), `ff7d61f219e4eb41489963c4bb5f57bea5bc2c69` (2026-07-17) | [MIT](https://github.com/LCAV/pyroomacoustics/blob/ff7d61f219e4eb41489963c4bb5f57bea5bc2c69/LICENSE); copyright 2014–2017 EPFL-LCAV | README and [RT60 Measurement Routine documentation](https://github.com/LCAV/pyroomacoustics/blob/ff7d61f219e4eb41489963c4bb5f57bea5bc2c69/docs/pyroomacoustics.experimental.rt60.rst): synthetic RIR / classical measurement comparison ideas | Documentation comparison only; remains not a dependency. |

The linked primary paper is Götz, Falcón Pérez, Schlecht and Pulkki,
[*Neural network for multi-exponential sound energy decay analysis*,
JASA 152(2), 942–953 (2022)](https://doi.org/10.1121/10.0013416).
Its public text was read through [arXiv:2205.09644](https://arxiv.org/abs/2205.09644);
the publisher's article is CC BY 4.0 according to its
[Crossref license metadata](https://api.crossref.org/works/10.1121/10.0013416).
Only the method concept is used. The project's own 2,245-parameter network,
synthetic generator and JSON weights are Apache-2.0 project material.

This limited review does not establish the licenses of all files,
dependencies or pretrained weights in the external projects and includes
no new patent search. Those materials are not shipped. A future source or
weight import would require its own full review and provenance entry.
Implementation and real-room validation limits are in
[LOCAL_DECAY_MODEL.md](LOCAL_DECAY_MODEL.md).

## Rules applied

* Repositories without a LICENSE file, or with a license that conflicts
  between README and source headers, are treated as **not usable**; only
  their publicly described functionality was considered.
* GPL/AGPL/LGPL projects were never copied, translated, or decompiled.
  Studying their documentation for feature scope is allowed and was done
  (DRC, Aliki).
* Proprietary software (REW) was consulted only through its public
  documentation for feature ideas; no binaries were inspected.
* MIT/BSD projects could have been adapted with attribution, but the core
  DSP was implemented independently from the papers and standards instead
  (project brief §2.5 D). If that changes, CODE_PROVENANCE.md and NOTICE must
  be updated first.

## Audit limitations (carried over from the full record)

DRC and Aliki source tarballs were not downloaded (licenses taken from their
documentation / download pages); ITA-Toolbox's HEAD commit and bundled
third-party list were blocked by the GitLab anti-bot challenge; only one or
two source files per repository were checked for license headers; build-time
dependencies of the audited projects were not audited to license-file level.
