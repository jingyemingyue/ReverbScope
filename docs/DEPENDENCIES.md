# Dependencies

Audit date: 2026-09-17 (installed versions from the development
environment). The full audit, with the URL of every LICENSE file read, the
contents of the macOS wheels and the per-package obligation notes, is in
[research/dependencies.md](research/dependencies.md). `scripts/dependency_licenses.py`
prints the installed metadata to keep this table in sync. PyPI metadata is
never the sole source; every license below was read from the upstream
repository.

Legend: **direct** = listed in `pyproject.toml`; **transitive** = pulled in
by a direct dependency; **runtime** / **dev**; "Yes*" = compatible with the
Apache-2.0 project with the redistribution obligations listed in §3.

## 1. Runtime dependencies

| Package | Version | Homepage / repository | License (upstream file) | Purpose in ReverbScope | Kind | Apache-2.0 compatible |
| --- | --- | --- | --- | --- | --- | --- |
| numpy | 2.5.3 | https://numpy.org / https://github.com/numpy/numpy | BSD-3-Clause (wheel bundles OpenBLAS BSD-3, libgfortran/libgcc GPL-3.0 WITH GCC-exception, libquadmath LGPL-2.1+) | arrays, FFT | direct, runtime | Yes* |
| scipy | 1.18.1 | https://scipy.org / https://github.com/scipy/scipy | BSD-3-Clause (+ bundled permissive components: Qhull, SuperLU, ARPACK, HiGHS, Boost, pybind11 ...) | filters, correlation, Hilbert, Welch, peak finding, resampling | direct, runtime | Yes* |
| soundfile | 0.14.0 | https://github.com/bastibe/python-soundfile | BSD-3-Clause; wheel bundles libsndfile 1.2.2 (LGPL-2.1-or-later) with FLAC/Ogg/Vorbis/Opus (BSD-3), mpg123 (LGPL-2.1), LAME (LGPL-2.0+) | WAV read/write | direct, runtime | Yes* (LGPL dynamic) |
| sounddevice | 0.5.6 | https://github.com/spatialaudio/python-sounddevice | MIT; wheel bundles PortAudio (MIT-style); Windows wheels also ship `*-asio.dll` built with the proprietary Steinberg ASIO SDK | device enumeration, play/record (Standalone Mode) | direct, runtime | Yes* (strip ASIO DLLs from Windows builds) |
| matplotlib | 3.11.2 | https://matplotlib.org / https://github.com/matplotlib/matplotlib | Matplotlib License (PSF-2.0-style); bundles FreeType (FTL), HarfBuzz, libraqm, SheenBidi (Apache-2.0), Qhull, Agg | plots (CLI scripts and GUI) | direct, runtime | Yes* |
| PySide6_Essentials | 6.11.2 | https://www.qt.io/qt-for-python / https://code.qt.io/cgit/pyside/pyside-setup.git | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only OR commercial; bundles Qt 6.11.2 | GUI (optional extra `gui`; Essentials only — not the PySide6 meta-package, which also pulls GPL Addons) | direct, runtime (optional) | Yes* (LGPL-3.0, dynamic; see §4) |
| shiboken6 | 6.11.2 | as PySide6 | as PySide6 | PySide6 binding runtime | transitive, runtime (optional) | Yes* |
| cffi | 2.1.1 | https://github.com/python-cffi/cffi | MIT-0 | soundfile/sounddevice C bindings | transitive, runtime | Yes |
| pycparser | 3.0 | https://github.com/eliben/pycparser | BSD-3-Clause | cffi dependency | transitive, runtime | Yes |
| typing-extensions | 4.16.0 | https://github.com/python/typing_extensions | PSF-2.0 | soundfile dependency | transitive, runtime | Yes |
| contourpy | 1.4.0 | https://github.com/contourpy/contourpy | BSD-3-Clause | matplotlib dependency | transitive, runtime | Yes |
| cycler | 0.12.1 | https://github.com/matplotlib/cycler | BSD-3-Clause | matplotlib dependency | transitive, runtime | Yes |
| fonttools | 4.65.0 | https://github.com/fonttools/fonttools | MIT | matplotlib dependency | transitive, runtime | Yes |
| kiwisolver | 1.5.1 | https://github.com/nucleic/kiwi | BSD-3-Clause | matplotlib dependency | transitive, runtime | Yes |
| packaging | 26.3 | https://github.com/pypa/packaging | Apache-2.0 OR BSD-2-Clause | matplotlib dependency | transitive, runtime | Yes |
| pillow | 12.3.0 | https://github.com/python-pillow/Pillow | MIT-CMU (HPND); bundles libjpeg, zlib, libtiff, freetype, ... (22 license blocks, no GPL) | matplotlib dependency | transitive, runtime | Yes* |
| pyparsing | 3.3.2 | https://github.com/pyparsing/pyparsing | MIT | matplotlib dependency | transitive, runtime | Yes |
| python-dateutil | 2.9.0.post0 | https://github.com/dateutil/dateutil | Apache-2.0 AND BSD-3-Clause (dual) | matplotlib dependency | transitive, runtime | Yes |
| six | 1.17.0 | https://github.com/benjaminp/six | MIT | python-dateutil dependency | transitive, runtime | Yes |

## 2. Development dependencies

| Package | Version | Repository | License | Purpose | Apache-2.0 compatible |
| --- | --- | --- | --- | --- | --- |
| pytest | 9.1.1 | https://github.com/pytest-dev/pytest | MIT | tests | Yes |
| pytest-cov | 7.1.0 | https://github.com/pytest-dev/pytest-cov | MIT | coverage | Yes |
| ruff | 0.16.8 | https://github.com/astral-sh/ruff | MIT | lint + format | Yes |
| mypy | 2.3.1 | https://github.com/python/mypy | MIT (+ PSF/Apache portions) | type checking | Yes |
| jsonschema | 4.26.0 | https://github.com/python-jsonschema/jsonschema | MIT | validate `to_dict` writers against shipped schemas (tests only) | Yes |
| hatchling | 1.32.4 | https://github.com/pypa/hatch | MIT | the build backend (`[build-system]`); also in `dev` so that `tests/unit/test_i18n.py` can exercise the wheel build hook (`hatch_build.py`) that compiles the `.mo` catalogs; not a runtime dependency | Yes |
| PyYAML | 6.0.3 | https://github.com/yaml/pyyaml | MIT | reads `.github/ISSUE_TEMPLATE/*.yml` in `tests/unit/test_issue_forms.py`, which keeps each English form and its Simplified Chinese counterpart in step (same fields, requirements and labels); tests only, not a runtime dependency | Yes |
| babel | (optional `i18n-dev`) | https://github.com/python-babel/babel | BSD-3-Clause | extract/compile gettext catalogs; not required at runtime | Yes |
| pyinstaller | (release workflow) | https://github.com/pyinstaller/pyinstaller | GPL-2.0-or-later WITH Bootloader-exception | one-directory desktop bundles; not a runtime dependency | Yes* (the bootloader that PyInstaller embeds in every frozen executable is covered by the Bootloader-exception, which lets it be shipped with a program under any license; ReverbScope does not import PyInstaller) |
| build | (CI and release workflow) | https://github.com/pypa/build | MIT | builds the sdist and wheel; not a runtime dependency | Yes |
| cyclonedx-bom | (release workflow on `v*` tags) | https://github.com/CycloneDX/cyclonedx-python | Apache-2.0 | SBOM attached to a draft Release; not a runtime dependency | Yes |
| Inno Setup | (Windows bundle job, when `iscc` is installed) | https://jrsoftware.org/isinfo.php | Inno Setup License (permissive, similar to modified BSD) | optional Windows installer around the one-directory zip; not imported by ReverbScope | Yes* (tool only) |
| Inno Setup Simplified Chinese messages (`ChineseSimplified.isl`, maintainer Zhenghan Yang) | Inno Setup repository tag `is-6_7_1`, `Files/Languages/Unofficial/`, SHA-256 pinned in `scripts/inno_chinese_messages.py` | https://github.com/jrsoftware/issrc | part of the Inno Setup source repository, whose `license.txt` (Inno Setup License, permissive) covers its files "except where otherwise noted"; the translation names its maintainer and states no other license | the installer's Chinese texts; fetched at build time (released Inno Setup up to 6.7 does not install it), compiled into `ReverbScope-Desktop-Windows-x64-Setup.exe`, not stored in this repository | Yes* (tool only) |

Evaluated and **not** adopted: `hypothesis` (MPL-2.0, file-level copyleft;
dev-only would be acceptable but it is not needed), `pytest-qt` (MIT; the
offscreen smoke test works without it).

## 3. Redistribution obligations (for a future packaged desktop app)

Nothing in this table restricts publishing ReverbScope's source under
Apache-2.0. The obligations below attach to a *frozen binary* that bundles
the wheels, and must be checked again at packaging time:

1. **Ship license texts and notices** for every bundled package: BSD/MIT
   notices (NumPy, SciPy, soundfile, sounddevice, cffi, pycparser, contourpy,
   cycler, kiwisolver, pillow, six, ...), the Matplotlib License, the
   FreeType credit line (required by the FTL; FreeType appears in matplotlib,
   Pillow and Qt), the Qhull license and source pointer (SciPy, matplotlib),
   the PortAudio license (not included in the sounddevice wheel), the Agg
   copyright line.
2. **LGPL components must remain replaceable shared libraries:** libsndfile
   (soundfile), Qt/PySide6/shiboken6, libquadmath. Do not statically link or
   obfuscate them; prefer one-directory / `.app` bundle layouts.
3. **Qt / PySide6:** see §4.
4. **Windows:** remove `libportaudio*-asio.dll` from the sounddevice wheel in
   the frozen build unless the Steinberg ASIO SDK license terms are accepted;
   ReverbScope does not need ASIO.
5. **GPL-only Qt modules must not be imported** (QtCharts, QtDataVisualization,
   QtGraphs, QtLottie, QtQuickTimeline, QtVirtualKeyboard, QtQuick3D,
   QtHttpServer, QtNetworkAuth, QtShaderTools). ReverbScope uses only QtCore,
   QtGui and QtWidgets; plots are matplotlib.

## 4. PySide6 / Qt check (project brief §2.8)

* **Versions in use:** PySide6 6.11.2 and shiboken6 6.11.2, bundling Qt
  6.11.2 (verified from the wheel's `QtCore.framework/Resources/Info.plist`).
* **Licensing options:** LGPL-3.0-only, GPL-2.0-only, GPL-3.0-only or a
  commercial license from The Qt Company. ReverbScope uses the **LGPL-3.0**
  option.
* **Distribution model:** ReverbScope imports PySide6 through the normal Python
  import mechanism; Qt is dynamically linked and is not modified. The `gui`
  extra depends on `PySide6_Essentials` only, so `PySide6_Addons` (GPL-only
  modules such as QtCharts / QtGraphs) is not installed with the project.
  Source distribution (sdist/wheel on PyPI) contains no Qt code at all, so
  the LGPL imposes nothing there.
* **Frozen app obligations (LGPL-3.0 §4):** the PySide6 wheels ship **no
  license files**, so a packaged ReverbScope must add: the LGPL-3.0 and
  GPL-3.0 texts (from the pyside-setup `LICENSES/` directory at tag 6.11.2),
  a prominent notice that Qt/PySide6 are used under the LGPL with a pointer
  to the Qt and PySide6 source (https://download.qt.io/official_releases/qt/6.11/6.11.2/,
  https://code.qt.io/cgit/pyside/pyside-setup.git/), the Qt third-party
  attributions for QtCore/QtGui/QtWidgets (PCRE2, zlib, libpng,
  libjpeg-turbo, HarfBuzz, FreeType, SQLite, Unicode data, MD4C, simdutf),
  and no EULA term restricting modification or reverse engineering of the
  Qt parts. The GUI's About dialog already carries the notice text.
* **Re-check before any binary release** (brief §2.8): confirm the PySide6
  version, that no GPL-only module is imported, and that the Qt libraries
  are still separate files in the bundle.

## 5. Candidate evaluated and not adopted

| Package | Version | License | Why not |
| --- | --- | --- | --- |
| pyroomacoustics | 0.10.1 | MIT (compiles Eigen MPL-2.0, nanoflann BSD-2, pybind11 BSD-3 into `libroom`; declares Cython as a runtime dependency) | ReverbScope needs only ESS, deconvolution and decay analysis, which are short clean-room functions; pyroomacoustics would add a compiled extension, an MPL-2.0 notice obligation and a large simulation library for no measurement benefit. Kept as a conceptual reference (THIRD_PARTY_REVIEW.md). |

## 6. Items marked UNKNOWN / NEEDS REVIEW

matplotlib's historical `ttconv` converter is **resolved**: matplotlib 3.10.0
is the first release whose wheels do not contain the `_ttconv` extension
(the cp312 wheels of 3.8.0, 3.9.0 and 3.9.4 still ship
`matplotlib/_ttconv.*.so`; checked 2026-09-24 by opening the wheels), so
ReverbScope requires matplotlib>=3.10; fonttools is used instead. Until
2026-09-24 this section said "3.8+", which was wrong: an environment with
matplotlib 3.8 or 3.9 contained ttconv.
`scripts/audit_wheel_contents.py` lists bundled shared libraries and license
files of the installed distributions (and of a downloaded `.whl`).

**Linux x86_64, CPython 3.12, opened 2026-09-22** in this environment:

| Package | Bundled shared libraries | Notes |
| --- | --- | --- |
| numpy 2.5.3 | `numpy.libs/libscipy_openblas64_-*.so`, `libgfortran-*.so.5`, `libquadmath-*.so.0` | Same OpenBLAS + GCC-runtime + LGPL libquadmath set as the 2026-09-17 macOS audit (which opened a `macosx_11_0` wheel; see the macOS note below); `LICENSE.txt` is in `.dist-info/licenses/`. |
| scipy 1.18.1 | `scipy.libs/libscipy_openblas-*.so`, two `libgfortran` builds, two `libquadmath` builds | `COPYING_QHULL.txt` is in the wheel; no extra GPL libraries beyond the GCC runtime exception set. |
| soundfile 0.14.0 | `_soundfile_data/libsndfile_x86_64.so` | `_soundfile_data/COPYING` is LGPL-2.1; replaceable via `cffi.dlopen` / system libsndfile. |
| sounddevice 0.5.6 | *none* | Linux wheel uses the system PortAudio (`libportaudio2`). No ASIO DLLs. |
| matplotlib 3.11.2 | extension modules only (`_qhull`, `ft2font`, `_backend_agg`, …) | No `ttconv` file. Qhull is compiled into `_qhull`. |
| Pillow 12.3.0 | `pillow.libs/` libjpeg, libtiff, libfreetype, libharfbuzz, libpng, libwebp, openjpeg, lcms2, … | MIT-CMU plus bundled codec SOs; no GPL library name in the `.so` list. |

**Windows win_amd64 CPython 3.12 wheels**, downloaded 2026-09-22
(`scripts/audit_wheel_contents.py --wheel`):

| Package | Bundled shared libraries | Notes |
| --- | --- | --- |
| numpy 2.5.3 | `numpy.libs/libscipy_openblas64_-*.dll`, `msvcp140-*.dll` | OpenBLAS + MSVC C++ runtime; no separate libgfortran / libquadmath DLLs. `LICENSE.txt` is under `.dist-info/licenses/`. |
| scipy 1.18.1 | `scipy.libs/libscipy_openblas-*.dll` | `COPYING_QHULL.txt` is in the wheel; OpenBLAS only at the `.libs/` layer. |
| soundfile 0.14.0 | `_soundfile_data/libsndfile_x64.dll` | `_soundfile_data/COPYING` is LGPL-2.1. |
| matplotlib 3.11.2 | extension modules only (`_qhull`, `ft2font`, `_backend_agg`, …) | No `ttconv` file. |
| Pillow 12.3.0 | extension modules only (`_imaging`, `_webp`, …) | No `pillow.libs/` folder; codecs are inside the `.pyd` files. MIT-CMU `LICENSE` in `.dist-info/licenses/`. |
| sounddevice 0.5.6 | `libportaudio{32,64,arm64}bit.dll` and matching `*-asio.dll`, plus a leftover `libportaudio.dylib` | ASIO DLLs remain a packaging gate (`scripts/check_bundle_contents.py`). |

**macOS arm64, CPython 3.12**, checked 2026-09-24 by opening the two numpy
2.5.3 arm64 wheels on PyPI: `numpy-2.5.3-cp312-cp312-macosx_14_0_arm64.whl`
— the wheel pip selects on macOS 14 and newer, and therefore on the
`macos-latest` CI runner — links Apple **Accelerate** and bundles **no**
shared library at all (there is no `numpy/.dylibs/` folder in it). The older
`macosx_11_0_arm64` wheel bundles `libscipy_openblas64_.dylib`,
`libgfortran.5.dylib`, `libquadmath.0.dylib` and `libgcc_s.1.1.dylib` under
`numpy/.dylibs/`. Which layout a frozen `.app` carries depends on the macOS
version of the machine that builds it, so the license bundle for a macOS
build must be generated on that machine; the libquadmath / libgfortran
obligations in §3 apply only to the OpenBLAS layout. The installed-wheel
audit test (`tests/unit/test_packaging_and_safety.py`) accepts either layout
and fails on a mixed one.

The license-bundle script still fails if a required package ships no license
text. None of these affect the source release.
