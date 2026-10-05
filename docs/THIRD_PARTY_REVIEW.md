# Third-party repository review

Audit date: 2026-09-17. Every repository that was studied while designing
ReverbScope is registered here with the result of its license check. The full
records (repository URL, author, commit/tag, verbatim license header,
multiple-license check, file headers, vendored code, NOTICE/COPYRIGHT/AUTHORS
files, patent statements, obligations, and the URL of every fact) are in
[research/reference_repos.md](research/reference_repos.md).

**Result: no source code was copied or adapted from any repository.** All of
them were used as *conceptual references* (feature design, algorithm names,
architecture ideas) or as ordinary dependencies. See CODE_PROVENANCE.md.

## Summary

| Project | Repository | License (from LICENSE file) | Copyleft | Affects Apache-2.0? | Classification for ReverbScope |
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
