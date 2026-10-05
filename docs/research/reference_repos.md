# ReverbScope — License audit of external reference repositories

Audit date: 2026-09-17. ReverbScope target license: Apache-2.0, core DSP written clean-room from papers/standards.
Method: GitHub REST API (`https://api.github.com/repos/<owner>/<repo>`, `/commits/<branch>`, `/releases/latest`, `/tags`, `/git/trees/<branch>`) for metadata; `raw.githubusercontent.com` for LICENSE / README / source files; project websites for non-GitHub projects. Every fact below carries the URL it was read from. Nothing was inferred from memory; where a file could not be fetched it is marked **UNKNOWN / NEEDS REVIEW**.

Classification key:
- **Conceptual reference only** — read for ideas/algorithms; do not copy code.
- **Code could be adapted with attribution** — license permits it if the copyright + permission notice is preserved (ReverbScope still prefers not to copy).
- **Do not use** — license unclear, incompatible, or no code available.

---

## 1. pyroomacoustics

| Field | Finding |
|---|---|
| Project name | pyroomacoustics |
| Repository URL | https://github.com/LCAV/pyroomacoustics |
| Author / organization | LCAV (EPFL Laboratory of Audiovisual Communications) — GitHub org `LCAV`; copyright holder "EPFL-LCAV" |
| Default branch / HEAD | `master`, HEAD `ff7d61f` (2026-07-17) — https://api.github.com/repos/LCAV/pyroomacoustics/commits/master |
| Latest release | `v0.10.1` (2026-05-01) — https://api.github.com/repos/LCAV/pyroomacoustics/releases/latest |
| License (SPDX) | **MIT** (GitHub license detection: MIT) |
| LICENSE file | https://raw.githubusercontent.com/LCAV/pyroomacoustics/master/LICENSE (19 lines, no "MIT License" title) |
| Verbatim head + copyright | ```Copyright (c) 2014-2017 EPFL-LCAV``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, ...``` |
| Multiple licenses? | No single-repo second license. **Build-time third-party fetch**: `external/CMakeLists.txt` uses CMake `FetchContent` to pull Eigen 5.0.1 (gitlab.com/libeigen/eigen), nanoflann v1.9.0, pybind11 v3.0.1 — https://raw.githubusercontent.com/LCAV/pyroomacoustics/master/external/CMakeLists.txt. These are not vendored in the tree (`external/` contains only `CMakeLists.txt` — https://api.github.com/repos/LCAV/pyroomacoustics/contents/external). Their licenses were not audited here. |
| File-level headers? | **No.** `pyroomacoustics/experimental/deconvolution.py` and `pyroomacoustics/experimental/measure_ir.py` start directly with imports, no copyright/license header. |
| Vendored third-party code? | None in-tree (top-level tree: `external/` = CMake only; `.gitmodules` is empty). C++ in `pyroomacoustics/libroom_src/` is first-party. `setup.py` notes "Script based on the cmake_example of pybind11 by Dean Moldovan". |
| NOTICE / COPYRIGHT / AUTHORS | None of NOTICE, COPYRIGHT, AUTHORS, CONTRIBUTORS present (all 404). `CONTRIBUTING.rst` exists. |
| Patent statements | None (MIT has no patent clause). |
| README vs LICENSE conflict | README "License" section reproduces MIT text but says `Copyright (c) 2014-2021 EPFL-LCAV` while LICENSE says `2014-2017` (https://raw.githubusercontent.com/LCAV/pyroomacoustics/master/README.rst, line 263). Year mismatch only; same license. |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes (keep copyright + permission notice). Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. MIT code can be included; the EPFL-LCAV notice must be kept for any copied portion. |
| Relevance | `experimental/deconvolution.py` (`deconvolve`, `wiener_deconvolve`), `experimental/signals.py` (`exponential_sweep`, `linear_sweep`), `experimental/measure_ir.py` — directly on-topic. |
| **Classification** | **Code could be adapted with attribution** (ReverbScope preference: conceptual reference only). |

---

## 2. python-acoustics

| Field | Finding |
|---|---|
| Project name | python-acoustics (`acoustics` package) |
| Repository URL | https://github.com/python-acoustics/python-acoustics |
| Author / organization | GitHub org `python-acoustics`; copyright "Python Acoustics" |
| Repo status | **Archived** (`archived: true` — https://api.github.com/repos/python-acoustics/python-acoustics). Last push 2023-12-10. |
| Default branch / HEAD | `master`, HEAD `99d7920` (2023-08-20) |
| Latest release | No GitHub releases; latest tag `v0.2.6` — https://api.github.com/repos/python-acoustics/python-acoustics/tags |
| License (SPDX) | **BSD-3-Clause** (GitHub detection: BSD-3-Clause) |
| LICENSE file | https://raw.githubusercontent.com/python-acoustics/python-acoustics/master/LICENSE (27 lines) |
| Verbatim head + copyright | ```Copyright (c) 2013, Python Acoustics``` <br> ```All rights reserved.``` <br> ```Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. * Neither the name of the {organization} nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.``` |
| Note on LICENSE text | Clause 3 contains the literal template placeholder `{organization}` (line 14) — the file was never filled in. Legally still recognisable as BSD-3-Clause, but worth flagging. |
| Multiple licenses? | No. |
| File-level headers? | **No.** `acoustics/room.py` and `acoustics/signal.py` begin with module docstrings, no copyright header. |
| Vendored third-party code? | None found (top-level: `acoustics/`, `docs/`, `examples/`, `tests/`, Nix files). |
| NOTICE / COPYRIGHT / AUTHORS | None (all 404). |
| Patent statements | None. |
| README vs LICENSE | Consistent: README "python-acoustics is distributed under the BSD 3-clause license. See LICENSE" (https://raw.githubusercontent.com/python-acoustics/python-acoustics/master/README.md line 29). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes (+ no-endorsement clause). Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | `acoustics/room.py` (T60 from impulse response, Schroeder integration, band filtering). |
| **Classification** | **Code could be adapted with attribution** (project archived — treat as conceptual reference; algorithms come from ISO 3382 anyway). |

---

## 3. pyfar

| Field | Finding |
|---|---|
| Project name | pyfar (python packages for acoustics research) |
| Repository URL | https://github.com/pyfar/pyfar |
| Author / organization | GitHub org `pyfar`; "The pyfar developers" (pyproject authors: `The pyfar developers <info@pyfar.org>`) |
| Default branch / HEAD | `main`, HEAD `32512a3` (2026-08-18) |
| Latest release | No GitHub releases; latest tag `v0.8.1` — https://api.github.com/repos/pyfar/pyfar/tags |
| License (SPDX) | **MIT** (GitHub detection: MIT; `pyproject.toml` classifier "License :: OSI Approved :: MIT License", `license = {file = "LICENSE"}`) |
| LICENSE file | https://raw.githubusercontent.com/pyfar/pyfar/main/LICENSE (19 lines) |
| Verbatim head + copyright | ```Copyright (c) [2020] [The pyfar developers]``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, ... subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, ...``` |
| Note on LICENSE text | Copyright line still has template square brackets `[2020] [The pyfar developers]`. Cosmetic; license identity is unambiguous MIT. |
| Multiple licenses? | No. |
| File-level headers? | **No.** `pyfar/dsp/dsp.py` and `pyfar/signals/deterministic.py` start with docstrings, no copyright header. |
| Vendored third-party code? | None found (top-level: `pyfar/`, `docs/`, `tests/`, CI files). |
| NOTICE / COPYRIGHT / AUTHORS | None (all 404). `CONTRIBUTING.rst`, `HISTORY.rst` present. |
| Patent statements | None. |
| README vs LICENSE | README.md contains **no license statement at all** (grep for "licen" empty — https://raw.githubusercontent.com/pyfar/pyfar/main/README.md). Not a conflict; pyproject + LICENSE agree on MIT. |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | `pyfar.signals.exponential_sweep_time/freq`, `pyfar.dsp.deconvolve` / regularized inversion, filter banks; pyfar-gallery has an ESS IR-measurement tutorial (https://pyfar-gallery.readthedocs.io/en/latest/gallery/no_binder/impulse_response_measurement.html). |
| **Classification** | **Code could be adapted with attribution** (ReverbScope preference: conceptual reference; it is also a reasonable runtime dependency). |

---

## 4. scipy

| Field | Finding |
|---|---|
| Project name | SciPy |
| Repository URL | https://github.com/scipy/scipy |
| Author / organization | GitHub org `scipy`; copyright "Enthought, Inc." and "SciPy Developers" |
| Default branch / HEAD | `main`, HEAD `f0371a8` (2026-09-16) |
| Latest release | `v1.18.1` (2026-08-21) — https://api.github.com/repos/scipy/scipy/releases/latest |
| License (SPDX) | **BSD-3-Clause** (GitHub detection: BSD-3-Clause) |
| LICENSE file | https://raw.githubusercontent.com/scipy/scipy/main/LICENSE.txt (30 lines) |
| Verbatim head + copyright | ```Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers.``` <br> ```All rights reserved.``` <br> ```Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse ...``` |
| Multiple licenses? | **Yes — many bundled components**, catalogued in https://raw.githubusercontent.com/scipy/scipy/main/LICENSES_bundled.txt: biteopt (MIT), fast_matrix_market (BSD-2), pystreambuf (BSD-3), fast_float (MIT), ryu (BSL-1.0), L-BFGS-B (BSD-3), LAPJVsp (BSD-3), SuperLU (BSD-3), ARPACK (BSD-3), Qhull (Qhull license), xsf ("BSD-3-Clause AND MIT AND BSD-3-Clause-LBNL AND Apache-2.0 WITH LLVM-exception"), pyduccfft/ducc0 (BSD-3), uarray (BSD-3), ampgo (MIT), pybind11 (BSD-3), HiGHS (MIT), Boost (BSL-1.0), Biasedurn (BSD-3), UNU.RAN (BSD-3), NumPy (BSD-3), array-api-compat (MIT), array-api-extra (MIT), Tempita (MIT), Chebfun (BSD-3), getLebedevSphere (BSD-2), prima. **None of the listed bundled files live under `scipy/signal/`.** |
| File-level headers? | Author lines only, no license text: `scipy/signal/_signaltools.py` → `# Author: Travis Oliphant / # 1999 -- 2002`; `scipy/signal/_waveforms.py` → `# Author: Travis Oliphant / # 2003 / # Feb. 2010: Updated by Warren Weckesser: Rewrote much of chirp() Added sweep_poly()`; `_spectral_py.py` docstring only. |
| Vendored third-party code? | **Yes**: `subprojects/` (git submodules per https://raw.githubusercontent.com/scipy/scipy/main/.gitmodules: array_api_compat, array_api_extra, boost_math, cobyqa, highs, unuran, xsf; plus in-tree biteopt, qhull_r, duccfft, pyprima) and in-tree items listed above. |
| NOTICE / COPYRIGHT / AUTHORS | No NOTICE, COPYRIGHT, AUTHORS, CONTRIBUTORS (all 404). `LICENSES_bundled.txt`, `CITATION.bib`, `.mailmap` present. |
| Patent statements | None in LICENSE.txt. |
| README vs LICENSE | README.rst has no license statement (grep empty) — no conflict. |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. ReverbScope already depends on SciPy at runtime; that imposes nothing on ReverbScope's own license. Copying SciPy *source* into ReverbScope would require keeping the SciPy BSD notice. |
| Relevance | `scipy.signal.chirp` (log sweep), `fftconvolve`, `butter`/`sosfiltfilt` (octave bands), `welch`, `minimum_phase`, `hilbert` — used as a library, not copied. |
| **Classification** | **Code could be adapted with attribution** — but the intended use is as a dependency; no source copying needed. |

---

## 5. Impulcifer

| Field | Finding |
|---|---|
| Project name | Impulcifer |
| Repository URL | https://github.com/jaakkopasanen/Impulcifer |
| Author / organization | Jaakko Pasanen (individual user) |
| Default branch / HEAD | `master`, HEAD `a4b6d45` (2023-11-25) |
| Latest release | No GitHub releases; single tag `1.0.0` — https://api.github.com/repos/jaakkopasanen/Impulcifer/tags |
| License (SPDX) | **MIT** (GitHub detection: MIT) |
| LICENSE file | https://raw.githubusercontent.com/jaakkopasanen/Impulcifer/master/LICENSE (21 lines) |
| Verbatim head + copyright | ```MIT License``` <br> ```Copyright (c) 2018 Jaakko Pasanen``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, ... The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.``` |
| Multiple licenses? | No. |
| File-level headers? | **No.** `impulse_response.py` and `impulse_response_estimator.py` begin with `# -*- coding: utf-8 -*-` then imports. |
| Vendored third-party code? | None found at top level (`data/`, `img/`, `research/` are data/doc dirs; not inspected file-by-file). `requirements.txt` pulls `git+https://github.com/jaakkopasanen/autoeq-pkg@1.2.5#autoeq` as a dependency (same author, MIT per AutoEq below). |
| NOTICE / COPYRIGHT / AUTHORS | None (all 404). `CHANGELOG.md` present. |
| Patent statements | None. |
| README vs LICENSE | README.md contains no license statement (grep empty — https://raw.githubusercontent.com/jaakkopasanen/Impulcifer/master/README.md). No conflict. |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | `impulse_response_estimator.py` (ESS generation + inverse filter), `impulse_response.py` (decay/plots), `room_correction.py`. Project is headphone/BRIR-oriented and dormant since 2023. |
| **Classification** | **Code could be adapted with attribution** (ReverbScope preference: conceptual reference only). |

---

## 6. AutoEq

| Field | Finding |
|---|---|
| Project name | AutoEq |
| Repository URL | https://github.com/jaakkopasanen/AutoEq |
| Author / organization | Jaakko Pasanen (individual user) |
| Default branch / HEAD | `master`, HEAD `7ae0f56` (2025-07-20) |
| Latest release | No GitHub releases; latest tag `4.1.2` — https://api.github.com/repos/jaakkopasanen/AutoEq/tags |
| License (SPDX) | **MIT** (GitHub detection: MIT; pyproject classifier "License :: OSI Approved :: MIT License") |
| LICENSE file | https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/LICENSE (21 lines) |
| Verbatim head + copyright | ```MIT License``` <br> ```Copyright (c) 2018-2022 Jaakko Pasanen``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, ... The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.``` |
| Multiple licenses? | Code: no. **Data**: `measurements/` and `results/` hold headphone measurement data derived from oratory1990, crinacle, Innerfidelity, Rtings, headphone.com (README lines 11-15 credit the sources). **No license statement for that data was found** in README or repo — data licensing is UNKNOWN. Irrelevant to ReverbScope (only smoothing ideas wanted). |
| File-level headers? | **No.** `autoeq/frequency_response.py`, `autoeq/peq.py` have no copyright header. |
| Vendored third-party code? | No third-party *code* dirs found (top-level: `autoeq/`, `dbtools/`, `webapp/`, `measurements/`, `results/`, `targets/`, `tests/`). |
| NOTICE / COPYRIGHT / AUTHORS | None (all 404). |
| Patent statements | None. |
| README / packaging vs LICENSE | README.md has no license section (grep empty). `pyproject.toml` `[tool.hatch.build] include` lists `"LICENCE"` (British spelling) while the file is `LICENSE` — packaging typo, not a license conflict (https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/pyproject.toml line 39). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | `frequency_response.py` smoothing (Savitzky–Golay via `scipy.signal.savgol_filter`, log-spaced interpolation). Only smoothing concepts are of interest. |
| **Classification** | **Conceptual reference only** (smoothing ideas). Code could legally be adapted with attribution, but nothing in it is needed. |

---

## 7. DRC — Digital Room Correction (Denis Sbragion)

| Field | Finding |
|---|---|
| Project name | DRC: Digital Room Correction |
| Repository / site URL | http://drc-fir.sourceforge.net/ ; SourceForge project https://sourceforge.net/projects/drc-fir/ ; docs https://drc-fir.sourceforge.net/doc/drc.html |
| Author / organization | Denis Sbragion (SourceForge maintainer `dsbragio`; contact d.sbragion@neomerica.it) |
| Latest release | 3.2.3 (SourceForge files: released 2024-02-22, 31.6 MB) — https://sourceforge.net/projects/drc-fir/ ; docs header "Version 3.2.3", document dated 2019-07-26 |
| Default branch / HEAD | N/A (SourceForge file releases; no git HEAD checked) |
| License (SPDX) | **GPL-2.0-or-later** |
| Evidence (verbatim) | Homepage: "DRC is available for free and is released under the terms of the GNU General Public License" (https://drc-fir.sourceforge.net/). SourceForge metadata: "GNU General Public License version 2.0 (GPLv2)" (https://sourceforge.net/projects/drc-fir/). Documentation front matter: ```Copyright © 2002-2019 Denis Sbragion``` / ```This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.``` (https://drc-fir.sourceforge.net/doc/drc.html) |
| LICENSE / COPYING file | **Not read** — the source tarball was not downloaded in this audit (see limitations). License determined from the project's own documentation and SourceForge metadata. |
| Multiple licenses? | Docs state: "This program uses the FFT routines from Takuya Ooura and the GNU Scientific Library (GSL) FFT routines." Companion tools `glsweep` and `lsconv` print "Copyright (C) 2002-2005 Denis Sbragion ... This program may be freely redistributed under the terms of the GNU GPL". Licenses of the Ooura FFT and GSL code as bundled were not verified. |
| File-level headers? | Not checked (no source fetched). |
| NOTICE / AUTHORS | Not checked. |
| Patent statements | GPL-2.0 has an implicit patent licence / liberty-or-death clause (§7); no separate statement seen. |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution/notice: yes. **Source disclosure: yes (strong copyleft).** |
| Affects ReverbScope's Apache-2.0? | **YES.** Incorporating GPL-2.0 code would force the combined work under GPL. Apache-2.0 is also not compatible with GPL-2.0-only (it is with GPL-3.0), so even one-way mixing is problematic. |
| Relevance | Sweep generation (`glsweep`), inverse-filter convolution (`lsconv`), room-correction filter design. Conceptually valuable; the documentation is a good reference for ESS parameter choices. |
| **Classification** | **Conceptual reference only** (GPL copyleft). Do not copy or translate code. |

---

## 8. Aliki (Fons Adriaensen)

| Field | Finding |
|---|---|
| Project name | Aliki |
| Repository / site URL | https://kokkinizita.linuxaudio.org/linuxaudio/ (index) ; downloads https://kokkinizita.linuxaudio.org/linuxaudio/downloads/index.html ; project page https://kokkinizita.linuxaudio.org/linuxaudio/aliki/index.html (currently says only "This page is under construction.") |
| Author / organization | Fons Adriaensen (site owner; no explicit copyright line seen on the pages fetched) |
| Latest release | Tarball listed as `aliki-0.3-0.tar.bz2 (360k)` on the downloads page. The index page text is stale: "Release 0.0.3-beta is available on the downloads page." (https://kokkinizita.linuxaudio.org/linuxaudio/index.html) |
| Default branch / HEAD | N/A (tarball distribution; no public git found) |
| License (SPDX) | **GPL-3.0** per the downloads-page license column: `aliki-0.3-0.tar.bz2 (360k) GPL3` (https://kokkinizita.linuxaudio.org/linuxaudio/downloads/index.html). "or later" status not determinable from the listing. |
| LICENSE / COPYING file | **Not read** — tarball not downloaded (see limitations). |
| Multiple licenses? | Unknown (tarball not inspected). Neighbouring libraries by the same author are listed as GPL3 (zita-resampler, zita-convolver). |
| File-level headers? | Not checked. |
| NOTICE / AUTHORS | Not checked. |
| Patent statements | GPL-3.0 §11 contains an explicit patent grant (if that is indeed the license text shipped). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Notice: yes. **Source disclosure: yes (strong copyleft).** |
| Affects ReverbScope's Apache-2.0? | **YES.** GPL-3.0 code would pull ReverbScope to GPL-3.0. (Apache-2.0 → GPL-3.0 one-way compatibility does not help ReverbScope stay Apache.) |
| Relevance | Full ESS measurement workflow (Farina method) in C++/JACK; the Aliki manual (PDF linked from the index page) is a useful conceptual reference. |
| **Classification** | **Conceptual reference only** (GPL copyleft). |

---

## 9. ITA-Toolbox (RWTH Aachen, MATLAB)

| Field | Finding |
|---|---|
| Project name | ITA-Toolbox for MATLAB |
| Repository URL | **Canonical: https://git.rwth-aachen.de/ita/toolbox** (RWTH GitLab). `https://github.com/ITA-RWTH/ITAToolbox` does **not exist** (GitHub API: "Not Found"); a GitHub repository search for "ITA-Toolbox matlab acoustics" returned 0 results. Website: https://www.ita-toolbox.org/ |
| Author / organization | Institute of Technical Acoustics (now Institute for Hearing Technology and Acoustics), RWTH Aachen University; head Prof. Michael Vorländer; contact toolbox-dev@akustik.rwth-aachen.de (from license.txt) |
| Default branch / HEAD | Branches `master` and `develop` both serve files; HEAD SHA **not obtainable** — the GitLab API and web UI are behind an Anubis anti-bot challenge; only the `/-/raw/` endpoint answered. |
| Latest release | Website offers "Current nightly build as zip file: ita-toolbox_nightly.zip" (https://www.ita-toolbox.org/download.php); no tagged release visible. |
| License (SPDX) | **BSD-4-Clause** (original BSD with advertising clause) |
| LICENSE file | https://git.rwth-aachen.de/ita/toolbox/-/raw/master/license.txt (5256 bytes; identical on `develop` and `HEAD`). Note the lowercase filename; `LICENSE`, `LICENSE.txt`, `COPYING` all 404. |
| Verbatim head + copyright | ```*                        ITA-Toolbox for MATLAB                        *``` / ```*  An Audio-Signal-Processing Toolbox for the needs of an Acoustician  *``` / ```*                          Copyright (c) 2011                          *``` / ```*       Institute of Technical Acoustics (RWTH Aachen University)      *``` / ```*                         All rights reserved.                         *``` / ```* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: 1. Redistributions of source code must retain the above copyright notice ... 2. Redistributions in binary form must reproduce the above copyright notice ... 3. All advertising materials mentioning features or use of this software must display the following acknowledgment: This product includes software developed by the Institute of Technical Acoustics (RWTH Aachen University). 4. Neither the name of the Institute of Technical Acoustics (RWTH Aachen University), nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.``` The file also lists active developers (Marco Berzborn, Hark Braren, Philipp Schäfer) and former developers. |
| Multiple licenses? | Website: "The ITA-Toolbox is distributed bundled with freely available third party packages." (https://www.ita-toolbox.org/download.php). **The bundled packages could not be enumerated** (sub-tree pages redirect to the Anubis challenge). Treat as: yes, third-party code present, terms unverified. |
| File-level headers? | Not checked (could not list source files). |
| Vendored third-party code? | Yes per website (see above); details unknown. |
| NOTICE / AUTHORS | No separate file found; developer list is inside `license.txt`. `Getting_Started.txt`: "by using this toolbox you accept the license agreement supplied in the 'license.txt' file." (https://git.rwth-aachen.de/ita/toolbox/-/raw/master/Getting_Started.txt) |
| Patent statements | None. |
| Website / paper vs LICENSE | Website: "The ITA-Toolbox is published under the original BSD-License." — consistent with the 4-clause text. DAGA 2017 paper (https://pub.dega-akustik.de/DAGA_2017/data/articles/000257.pdf, p. 222/223): "Since 2010, the ITA-Toolbox is available as open source software under the Berkeley Software Distribution (BSD) license" / "licensed under the BSD license" — does not state the clause count. **Do not mistake it for BSD-3-Clause: the advertising clause (3) is present.** |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes **plus the advertising-acknowledgment obligation** ("This product includes software developed by the Institute of Technical Acoustics (RWTH Aachen University)"). Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | Not copyleft, so ReverbScope could remain Apache-2.0, but any adapted code would add a BSD-4-Clause acknowledgment obligation to ReverbScope's NOTICE/README and marketing material. BSD-4-Clause is also GPL-incompatible (a downstream concern for anyone combining ReverbScope with GPL code). It is also MATLAB, so nothing is directly reusable in Python. |
| Relevance | Room-acoustics application (T60, C80, D50, ISO 3382 parameters), measurement classes (itaMSTF), multiple-exponential-sweep method (Dietrich et al.). |
| **Classification** | **Conceptual reference only** (MATLAB; BSD-4-Clause advertising clause; unverified bundled third-party code). |

---

## 10. Room EQ Wizard (REW)

| Field | Finding |
|---|---|
| Project name | Room EQ Wizard (REW) |
| Site URL | https://www.roomeqwizard.com/ ; EULA https://www.roomeqwizard.com/eula.html |
| Author / organization | John Mulcahy — "Copyright © John Mulcahy 2026 All Rights Reserved" (homepage) |
| Version | Homepage text fetched states "V5.31.3 (released 25th July 2024)" — the page may show an older stable version; not material to this audit. |
| Default branch / HEAD | N/A — **closed source, no repository** |
| License (SPDX) | **Proprietary freeware (no SPDX id)** — free base version plus paid "Pro upgrade"; governed by an EULA. |
| EULA key clauses (verbatim) | "Distribution of copies of Room EQ Wizard is strictly forbidden without the prior written consent of John Mulcahy." / "You may not, and may not attempt to, modify, reverse engineer, disassemble or decompile Room EQ Wizard." / "John Mulcahy retains sole and exclusive ownership of all right, title and interest in and to Room EQ Wizard and all Intellectual Property rights relating thereto." / grants "a limited, non-exclusive, non-transferable license ... to use Room EQ Wizard without charge." (https://www.roomeqwizard.com/eula.html) |
| Multiple licenses? | N/A. |
| Source code available? | **No.** |
| Modification / redistribution / attribution / copyleft | Modify: **no**. Redistribute: **no**. Reverse-engineering: **prohibited**. Copyleft: N/A. |
| Affects ReverbScope's Apache-2.0? | No code can be used at all. Using REW's public documentation to understand *what* features users expect (RT60/EDT/T20/T30 reporting, waterfall, ETC) is fine; replicating its behaviour must be from first principles/standards, never from decompilation. |
| **Classification** | **Do not use (proprietary; no source).** Feature-level conceptual reference only, from public docs. |

---

## 11. acoular

| Field | Finding |
|---|---|
| Project name | Acoular — Acoustic testing and source mapping software |
| Repository URL | https://github.com/acoular/acoular |
| Author / organization | GitHub org `acoular`; copyright "Acoular Development Team"; AUTHORS.rst lists Ennes Sarradj, Gert Herold, Adam Kujawski, Tom Gensch, Simon Jekosch, Mikolaj Czuchaj, Art Pelling; "started in 2006 by Ennes Sarradj ... In 2015 it was published under an open source license (BSD)" (https://raw.githubusercontent.com/acoular/acoular/master/AUTHORS.rst) |
| Default branch / HEAD | `master`, HEAD `13d3d7d` (2026-09-09) |
| Latest release | `v26.08` (2026-08-17) — https://api.github.com/repos/acoular/acoular/releases/latest |
| License (SPDX) | **BSD-3-Clause** (GitHub detection: BSD-3-Clause; pyproject `license = {file = "LICENSE"}`, classifier "BSD License") |
| LICENSE file | https://raw.githubusercontent.com/acoular/acoular/master/LICENSE (28 lines) |
| Verbatim head + copyright | ```BSD 3-Clause License``` <br> ```Copyright (c) Acoular Development Team``` <br> ```Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products ...``` (no year in the copyright line) |
| Multiple licenses? | No. |
| File-level headers? | **Yes.** `acoular/sources.py` and `acoular/tprocess.py` both start with `# Copyright (c) Acoular Development Team.` (no SPDX tag, no license text). |
| Vendored third-party code? | None found (top-level: `acoular/`, `docs/`, `examples/`, `tests/`, `recipe.local/` — conda recipe, not inspected). |
| NOTICE / COPYRIGHT / AUTHORS | `AUTHORS.rst` **present**; `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.rst` present; no NOTICE/COPYRIGHT. |
| Patent statements | None. |
| README vs LICENSE | Consistent: "Acoular is a Python module for acoustic beamforming that is distributed under the BSD 3-clause license" (https://raw.githubusercontent.com/acoular/acoular/master/README.md line 9). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | Microphone-array beamforming / source mapping; only tangential to a single-mic room analyzer (time-domain block processing, octave-band filtering ideas). |
| **Classification** | **Conceptual reference only** (low relevance; code could legally be adapted with attribution). |

---

## 12. pyrirtool

| Field | Finding |
|---|---|
| Project name | pyrirtool — "Measuring room impulse responses with python and sounddevice" |
| Repository URL | https://github.com/maj4e/pyrirtool |
| Author / organization | Maja Taseska (individual user `maj4e`), KU Leuven ESAT-STADIUS (README "Authors" section; `measure.py` header banner "Author: Maja Taseska, ESAT-STADIUS, KU LEUVEN") |
| Default branch / HEAD | `master`, HEAD `cc64f50` (2019-06-30). Last push 2019-06-30 (dormant). |
| Latest release | None — no releases, no tags (https://api.github.com/repos/maj4e/pyrirtool/tags → `[]`) |
| License (SPDX) | **MIT** (GitHub detection: MIT) |
| LICENSE file | https://raw.githubusercontent.com/maj4e/pyrirtool/master/LICENSE.md (21 lines) |
| Verbatim head + copyright | ```MIT License``` <br> ```Copyright (c) 2019 Maja Taseska``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, ... The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.``` |
| Multiple licenses? | No. |
| File-level headers? | `measure.py`: author banner (name/affiliation) but **no license text**; `stimulus.py`: **no header**. |
| Vendored third-party code? | None (repo is 6 Python files + README + LICENSE.md). |
| NOTICE / COPYRIGHT / AUTHORS | None; README has an "Authors" section. |
| Patent statements | None. |
| README vs LICENSE | Consistent: "This project is licensed under the MIT License - see the LICENSE.md file for details" (https://raw.githubusercontent.com/maj4e/pyrirtool/master/README.md line 106). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No. |
| Relevance | Very high: ESS stimulus class (`stimulus.py`), inverse filter, sounddevice-based play/record (`measure.py`), Farina method. |
| **Classification** | **Code could be adapted with attribution** (ReverbScope preference: conceptual reference only). |

---

## 13. GitHub search — "exponential sine sweep impulse response python"

Searches run: `github "exponential sine sweep" impulse response measurement python` and `github python room impulse response measurement sine sweep deconvolution farina RT60 tool` (WebSearch, 2026-09-17). Top relevant hits audited below; pyrirtool and the pyfar gallery also surfaced and are covered above.

### 13a. jmrplens/phonometry

| Field | Finding |
|---|---|
| Repository URL | https://github.com/jmrplens/phonometry ("formerly PyOctaveBand") |
| Author | José Manuel Requena Plens (individual user `jmrplens`) |
| Default branch / HEAD | `main`, HEAD `61a23ac` (2026-09-17); actively developed (116 stars) |
| Latest release | Not queried (release API not called for this repo); `VERSION`, `CHANGELOG.md`, `CITATION.cff`, `.zenodo.json` present. |
| License (SPDX) | **MIT** (GitHub detection: MIT; `pyproject.toml` `license = "MIT"`, `license-files = ["LICENSE"]`) |
| LICENSE file | https://raw.githubusercontent.com/jmrplens/phonometry/main/LICENSE (21 lines): ```MIT License``` / ```Copyright (c) 2020-2026 José Manuel Requena Plens``` / standard MIT permission text. |
| File-level headers? | **Yes** (copyright only): `src/phonometry/__init__.py` line 1 `#  Copyright (c) 2020. Jose Manuel Requena Plens`. |
| Multiple licenses / vendored code? | No vendored third-party code seen at top level. README (line 63-65) notes the optional `[audio]` extra installs python-soundfile "whose wheel bundles libsndfile under the LGPL-2.1 (dynamically linked)". |
| NOTICE / AUTHORS | None; README MIT badge links to LICENSE (consistent). |
| Copyleft? | No. Affects Apache-2.0? No. |
| Relevance | Claims standards-based (ISO 3382 etc.) room acoustics, Farina ESS deconvolution with harmonic separation, synchronized swept sine — a very close analogue to ReverbScope's goals. |
| **Classification** | **Code could be adapted with attribution** (ReverbScope preference: conceptual reference; its per-standard documentation is useful for clean-room work). |

### 13b. baranovmv/RoomResponse

| Field | Finding |
|---|---|
| Repository URL | https://github.com/baranovmv/RoomResponse |
| Author | Mikhail Baranov (individual user) |
| Default branch / HEAD | `master`, HEAD `0a52651` (2018-10-10); dormant |
| License (SPDX) | **MIT** — https://raw.githubusercontent.com/baranovmv/RoomResponse/master/LICENSE: ```MIT License``` / ```Copyright (c) 2016 Mikhail Baranov``` / standard MIT text (21 lines) |
| File-level headers? | No (`room_response_estimator.py` starts with imports; docstring cites Farina's paper). |
| Vendored code / NOTICE / AUTHORS | None. README has no license statement (no conflict). |
| Copyleft? | No. Affects Apache-2.0? No. |
| **Classification** | **Code could be adapted with attribution** (small experimental repo; conceptual reference preferred). |

### 13c. spatialaudio/sweep

| Field | Finding |
|---|---|
| Repository URL | https://github.com/spatialaudio/sweep — "Simulation environment for sweep-based room impulse response measurements (student project)" |
| Author | Franz Plocksties (copyright holder); hosted under org `spatialaudio` |
| Default branch / HEAD | `master`, HEAD `003bc0e` (2017-06-10); dormant |
| License (SPDX) | **MIT** — https://raw.githubusercontent.com/spatialaudio/sweep/master/LICENSE.txt: ```The MIT License (MIT)``` / ```Copyright (c) 2015 Franz Plocksties``` / standard MIT text (22 lines) |
| File-level headers? | No (`calculation.py` starts with a docstring). |
| Vendored code / NOTICE / AUTHORS | None. README has no license statement (no conflict). |
| Copyleft? | No. Affects Apache-2.0? No. |
| **Classification** | **Code could be adapted with attribution** (conceptual reference preferred; simulation-oriented). |

### 13d. Hakim-El/Project_Course_2022

| Field | Finding |
|---|---|
| Repository URL | https://github.com/Hakim-El/Project_Course_2022 — "Measurement Framework for Room Impulse Response Dataset and Acoustic Source Calibration" |
| Default branch / HEAD | `main`, HEAD `7a13434` (2022-07-14) |
| License | **NO LICENSE FILE** (checked LICENSE, LICENSE.txt, LICENSE.md, LICENSE.rst, COPYING, LICENCE, UNLICENSE — all 404; GitHub API `license: null`; README has no license statement). |
| **Classification** | **License unclear — no source code copied.** (All-rights-reserved by default.) |

### 13e. pengowray/sweep

| Field | Finding |
|---|---|
| Repository URL | https://github.com/pengowray/sweep — "Online sine sweep generator for impulse response / convolution reverb" (**JavaScript**, not Python) |
| Author | Pengo Wray; `main`, HEAD `336c3ba` (2026-06-19) |
| License (SPDX) | **MIT** — https://raw.githubusercontent.com/pengowray/sweep/main/LICENSE: ```MIT License``` / ```Copyright (c) 2026 Pengo Wray```. README "License" section says only "Open source. Free to use for any purpose." — looser wording than the file, but not contradictory. |
| **Classification** | **Conceptual reference only** (different language; MIT would permit adaptation with attribution). |

### 13f. Single-file gists (no LICENSE)

- https://gist.github.com/akashrajkn/215b0bba02d9a1ce43fbc9842dead43a — one file `impulse_response.py` (librosa-based ESS IR). No LICENSE file in the gist.
- https://gist.github.com/40c485b4b2d4e8ad251fef2e96953021 — "Angelo Farina's Exponential Sine Sweep" Python 3 gist. Not fetched; gists carry no license unless stated.

**Classification: License unclear — no source code copied.**

---

## 14. python-sounddevice (runtime dependency)

| Field | Finding |
|---|---|
| Project name | sounddevice — "Play and Record Sound with Python" |
| Repository URL | https://github.com/spatialaudio/python-sounddevice |
| Author / organization | Matthias Geier (copyright holder; pyproject author `Matthias Geier <Matthias.Geier@gmail.com>`); hosted under org `spatialaudio` |
| Default branch / HEAD | `master`, HEAD `626fcb0` (2026-08-22) |
| Latest release | `0.5.6` (2026-08-17) — https://api.github.com/repos/spatialaudio/python-sounddevice/releases/latest |
| License (SPDX) | **MIT** (GitHub detection: MIT; `pyproject.toml` `license = "MIT"`) |
| LICENSE file | https://raw.githubusercontent.com/spatialaudio/python-sounddevice/master/LICENSE (19 lines) |
| Verbatim head + copyright | ```Copyright (c) 2015-2025 Matthias Geier``` <br> ```Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, ... The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", ...``` |
| Multiple licenses? | Repo code: no. **Bundled binaries via git submodule** `src/_sounddevice_data/portaudio-binaries` → https://github.com/spatialaudio/portaudio-binaries whose README "Copyright" section states: "PortAudio by Ross Bencina and Phil Burk, MIT License." and "Steinberg Audio Stream I/O API by Steinberg Media Technologies GmbH." (https://raw.githubusercontent.com/spatialaudio/portaudio-binaries/master/README.md lines 29-34). The ASIO SDK is under Steinberg's own terms (not audited); it only matters for the Windows binary wheels. |
| File-level headers? | **Yes.** `src/sounddevice.py` opens with `# Copyright (c) 2015-2026 Matthias Geier` followed by the full MIT permission text (note year 2026 vs LICENSE file's 2025 — trivial drift). |
| **Example scripts license** | `examples/rec_unlimited.py`, `examples/play_file.py` carry **no license header** (shebang + docstring only), and `doc/examples.rst` contains no separate license/public-domain statement (grep empty). They are therefore covered by the repository's MIT LICENSE: copying an example into ReverbScope requires keeping the Matthias Geier MIT notice. |
| NOTICE / COPYRIGHT / AUTHORS | None (all 404). `CONTRIBUTING.rst`, `NEWS.rst` present. |
| Patent statements | None. |
| README vs LICENSE | Consistent: "License: MIT -- see the file LICENSE for details." (https://raw.githubusercontent.com/spatialaudio/python-sounddevice/master/README.rst line 15-16). |
| Modification / redistribution / attribution / notice / copyleft | Modify: yes. Redistribute: yes. Attribution: yes. Preserve notice: yes. Source disclosure: no. **Copyleft: no.** |
| Affects ReverbScope's Apache-2.0? | No, as a dependency. If example code is adapted, add the MIT notice to ReverbScope's third-party notices. |
| **Classification** | **Code could be adapted with attribution** (dependency; examples reusable with the MIT notice). |

---

## 15. python-soundfile (runtime dependency)

| Field | Finding |
|---|---|
| Project name | soundfile (python-soundfile) — libsndfile/CFFI/NumPy audio I/O |
| Repository URL | https://github.com/bastibe/python-soundfile |
| Author / organization | Bastian Bechtold (individual user `bastibe`; setup.py author `Bastian Bechtold <bastibe.dev@mailbox.org>`) |
| Default branch / HEAD | `master`, HEAD `3503941` (2026-07-14) |
| Latest release | `0.14.0` (2026-06-06) — https://api.github.com/repos/bastibe/python-soundfile/releases/latest ; `soundfile.py` `__version__ = "0.14.0"` |
| License (SPDX) | **BSD-3-Clause** (GitHub detection: BSD-3-Clause; setup.py `license='BSD 3-Clause License'`) |
| LICENSE file | https://raw.githubusercontent.com/bastibe/python-soundfile/master/LICENSE (29 lines) |
| Verbatim head + copyright | ```Copyright (c) 2013, Bastian Bechtold``` <br> ```All rights reserved.``` <br> ```Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. * Neither the name of python-soundfile nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.``` |
| Multiple licenses? | **Yes, for bundled binaries.** `licensing/license_notes.md` (https://raw.githubusercontent.com/bastibe/python-soundfile/master/licensing/license_notes.md): "While python-soundfile itself is licensed under the BSD-3-Clause license, it links against media libraries that are licensed under a mixture of LGPL and BSD licenses within libsndfile." It then lists per-library copyrights: libflac (BSD-3-Clause component), libmp3lame (LGPL-2+), libmpg123, etc. Git submodule `_soundfile_data` → https://github.com/bastibe/libsndfile-binaries whose README states: "Libsndfile by Erik de Castro Lopo, GNU Lesser General Public License (LGPL)", FLAC BSD-3, Ogg Vorbis BSD-3, Opus BSD-3, "Mpg123 ... LGPL v2.1", "Lame ... LGP v2 [sic]". |
| File-level headers? | **No.** `soundfile.py` begins with a module docstring and `__version__`; no copyright header. |
| Vendored third-party code? | Only the binary submodule above (`_soundfile_data`, shipped inside wheels with a `COPYING` file per setup.py `package_data`). No third-party Python source. |
| NOTICE / COPYRIGHT / AUTHORS | No NOTICE/AUTHORS; `licensing/license_notes.md` acts as the third-party notice file. |
| Patent statements | None. |
| README vs LICENSE | Consistent: "python-soundfile is BSD licensed (BSD 3-Clause License). (c) 2013, Bastian Bechtold" (https://raw.githubusercontent.com/bastibe/python-soundfile/master/README.rst lines 21-22). |
| Modification / redistribution / attribution / notice / copyleft | soundfile itself: Modify yes, redistribute yes, attribution yes, notice yes, source disclosure no, **copyleft no**. The bundled libsndfile is **LGPL (weak copyleft)** — dynamically linked; obligations attach to whoever redistributes the binary (the wheel publisher), not to a pip-installing Apache-2.0 project. |
| Affects ReverbScope's Apache-2.0? | No, when used as a normal pip dependency. If ReverbScope ever bundles the soundfile wheel/libsndfile in its own installer, the LGPL notice/relinking obligations for libsndfile apply. |
| **Classification** | **Code could be adapted with attribution** (dependency; no need to copy source). |

---

## Summary table

| # | Project | License (SPDX) | Copyleft? | Affects Apache-2.0 project? | Classification for ReverbScope |
|---|---|---|---|---|---|
| 1 | pyroomacoustics | MIT | No | No (keep EPFL-LCAV notice if copied) | Code could be adapted with attribution (prefer conceptual) |
| 2 | python-acoustics (archived) | BSD-3-Clause (template `{organization}` left in) | No | No | Code could be adapted with attribution (prefer conceptual) |
| 3 | pyfar | MIT (bracketed placeholders in copyright line) | No | No | Code could be adapted with attribution (prefer conceptual / dependency) |
| 4 | scipy | BSD-3-Clause (+ many bundled permissive licenses, none in `scipy/signal`) | No | No (dependency) | Code could be adapted with attribution — use as dependency |
| 5 | Impulcifer | MIT | No | No | Code could be adapted with attribution (prefer conceptual) |
| 6 | AutoEq | MIT (measurement *data* license unknown) | No | No | Conceptual reference only (smoothing ideas) |
| 7 | DRC (Sbragion) | GPL-2.0-or-later | **Yes (strong)** | **Yes — would force GPL** | Conceptual reference only |
| 8 | Aliki (Adriaensen) | GPL-3.0 (per downloads page; COPYING not read) | **Yes (strong)** | **Yes — would force GPL** | Conceptual reference only |
| 9 | ITA-Toolbox (MATLAB) | BSD-4-Clause (advertising clause) | No | No, but adds acknowledgment obligation; GPL-incompatible downstream | Conceptual reference only |
| 10 | Room EQ Wizard | Proprietary freeware EULA (no source) | N/A | No code exists to use | Do not use (proprietary) — feature ideas from public docs only |
| 11 | acoular | BSD-3-Clause | No | No | Conceptual reference only (low relevance) |
| 12 | pyrirtool | MIT | No | No | Code could be adapted with attribution (prefer conceptual) |
| 13a | phonometry | MIT | No | No | Code could be adapted with attribution (prefer conceptual) |
| 13b | RoomResponse (baranovmv) | MIT | No | No | Code could be adapted with attribution (prefer conceptual) |
| 13c | spatialaudio/sweep | MIT | No | No | Code could be adapted with attribution (prefer conceptual) |
| 13d | Hakim-El/Project_Course_2022 | **None** | Unknown | Unknown | License unclear — no source code copied |
| 13e | pengowray/sweep (JS) | MIT | No | No | Conceptual reference only |
| 13f | ESS gists (akashrajkn; Farina gist) | **None** | Unknown | Unknown | License unclear — no source code copied |
| 14 | python-sounddevice (+ examples) | MIT (PortAudio binaries MIT; ASIO SDK Steinberg terms) | No | No (keep MIT notice if examples copied) | Code could be adapted with attribution (dependency) |
| 15 | python-soundfile | BSD-3-Clause (bundled libsndfile LGPL, dynamic) | No (LGPL only in bundled binary) | No as pip dependency | Code could be adapted with attribution (dependency) |

Practical rule for ReverbScope: every green-lit repo above is MIT/BSD, so nothing here threatens the Apache-2.0 plan **as long as DRC, Aliki and REW are never copied, translated, or decompiled**. If any MIT/BSD snippet is ever adapted despite the clean-room preference, record it in a `THIRD_PARTY_NOTICES` file with the exact copyright line quoted above.

---

## Audit limitations

1. **DRC and Aliki source tarballs were not downloaded**, so their in-tree `COPYING`/license headers were not read. DRC's license comes from its own documentation (`drc.html` front matter, GPL-2.0-or-later wording) and SourceForge metadata (GPLv2); Aliki's from the author's downloads-page license column ("GPL3"). Whether Aliki is GPL-3.0-only or -or-later is **UNKNOWN / NEEDS REVIEW**. The licenses of DRC's embedded Ooura FFT and GSL FFT routines were not verified.
2. **ITA-Toolbox**: the RWTH GitLab web UI and API are behind an Anubis anti-bot challenge; only `/-/raw/` worked. Consequently: no HEAD commit SHA, no tag/release list, no enumeration of the "bundled third party packages" the website mentions, and no source-file header check. The 4-clause license text itself was read verbatim.
3. **REW**: findings rely on the public homepage and EULA page as rendered on 2026-09-17; the version string on the homepage (V5.31.3, 2024) may not reflect the current build. No terms-of-use page beyond the EULA was read.
4. **Third-party build/binary dependencies were not audited to license-file level**: pyroomacoustics' CMake-fetched Eigen/nanoflann/pybind11; sounddevice's ASIO SDK inside the PortAudio binaries; soundfile's full libsndfile dependency chain (only the project's own `license_notes.md` and `libsndfile-binaries` README were read). SciPy's bundled components were taken from `LICENSES_bundled.txt` without opening each license file.
5. **AutoEq measurement/result data** licensing could not be determined (no statement found); irrelevant to ReverbScope's stated use.
6. **Source-header checks covered 1-2 files per repo** as requested, not the whole tree; repositories with no headers in those files may still have headers elsewhere.
7. **Release information** for phonometry was not queried (tags/releases API not called). For Impulcifer, AutoEq, pyfar and python-acoustics GitHub has no "Releases", so the newest *tag* is reported instead.
8. GitHub license detection (`license.spdx_id`) was used only as corroboration; the primary source for every license is the raw LICENSE file quoted in each section.
9. The Farina ESS gist (`40c485b4...`) was not fetched; it is listed only because it appeared in search results and gists normally carry no license.
