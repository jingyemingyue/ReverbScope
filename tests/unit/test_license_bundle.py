from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_license_bundle_has_no_unresolved(tmp_path: Path) -> None:
    bundle_mod = _load("build_license_bundle")
    dest = tmp_path / "THIRD_PARTY_LICENSES"
    unresolved = bundle_mod.build(dest)
    required_present = {"numpy", "scipy", "soundfile", "sounddevice", "matplotlib"}
    missing_required = [name for name in required_present if name in unresolved]
    assert missing_required == []
    index = (dest / "INDEX.txt").read_text(encoding="utf-8")
    assert "ttconv: resolved" in index
    assert (dest / "_notices" / "pyside6.txt").is_file()
    if unresolved:
        assert "PySide6" not in "".join(unresolved)


def test_license_bundle_ships_verbatim_lgpl_gpl_and_portaudio_texts(tmp_path: Path) -> None:
    """DEPENDENCIES.md §3-§4: the wheels omit these texts, so the repo carries them."""
    bundle_mod = _load("build_license_bundle")
    dest = tmp_path / "THIRD_PARTY_LICENSES"
    bundle_mod.build(dest)
    lgpl = (dest / "_texts" / "LGPL-3.0.txt").read_text(encoding="utf-8")
    gpl = (dest / "_texts" / "GPL-3.0.txt").read_text(encoding="utf-8")
    portaudio = (dest / "_texts" / "PortAudio-LICENSE.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl and "Version 3, 29 June 2007" in lgpl
    assert "GNU GENERAL PUBLIC LICENSE" in gpl and "Version 3, 29 June 2007" in gpl
    assert "TERMS AND CONDITIONS" in gpl
    assert "Ross Bencina and Phil Burk" in portaudio
    assert "The above copyright notice and this permission notice" in portaudio
    assert "_texts/LGPL-3.0.txt" in (dest / "_notices" / "pyside6.txt").read_text(encoding="utf-8")


def test_license_bundle_reports_missing_qt_texts_when_pyside_is_installed(tmp_path: Path) -> None:
    bundle_mod = _load("build_license_bundle")
    dest = tmp_path / "THIRD_PARTY_LICENSES"
    unresolved = bundle_mod.build(dest, texts_dir=tmp_path / "no-such-dir")
    qt_installed = bundle_mod._installed("PySide6_Essentials") or bundle_mod._installed("PySide6")
    missing = {item for item in unresolved if item.startswith("text:")}
    if qt_installed:
        assert missing == {"text:LGPL-3.0.txt", "text:GPL-3.0.txt", "text:qt-third-party.txt"}
    else:
        assert missing == set()


def test_macos_info_plist_declares_microphone() -> None:
    plist = Path("packaging/macos/Info.plist").read_text(encoding="utf-8")
    assert "NSMicrophoneUsageDescription" in plist
    assert "measurement microphone" in plist
    entitlements = Path("packaging/macos/entitlements.plist").read_text(encoding="utf-8")
    assert "com.apple.security.device.audio-input" in entitlements
    spec = Path("packaging/reverbscope.spec").read_text(encoding="utf-8")
    assert "packaging" in spec and "Info.plist" in spec


def test_bundle_gate_rejects_asio_and_qtcharts(tmp_path: Path) -> None:
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    (tree / "ok").mkdir(parents=True)
    (tree / "ok" / "QtCore.so").write_text("", encoding="utf-8")
    (tree / "ok" / "QtCharts.pyi").write_text("", encoding="utf-8")
    assert gate.check(tree) == []
    (tree / "libportaudio-asio.dll").write_text("", encoding="utf-8")
    charts = tree / "PySide6"
    charts.mkdir()
    (charts / "QtCharts.abi3.so").write_text("", encoding="utf-8")
    errors = gate.check(tree)
    assert any("ASIO" in item for item in errors)
    assert any("GPL-only" in item or "QtCharts" in item for item in errors)


def test_bundle_gate_catches_versioned_qt6_libraries_and_frameworks(tmp_path: Path) -> None:
    """Library file names carry the Qt major version and, on Linux, a version suffix."""
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    lib = tree / "PySide6" / "Qt" / "lib"
    lib.mkdir(parents=True)
    (lib / "libQt6Widgets.so.6").write_text("", encoding="utf-8")
    assert gate.check(tree) == []
    (lib / "libQt6QuickTimeline.so.6").write_text("", encoding="utf-8")
    (tree / "Qt6VirtualKeyboard.dll").write_text("", encoding="utf-8")
    framework = tree / "Frameworks" / "QtCharts.framework" / "Versions" / "A"
    framework.mkdir(parents=True)
    (framework / "QtCharts").write_text("", encoding="utf-8")
    (framework / "Resources").mkdir()
    (framework / "Resources" / "Info.plist").write_text("", encoding="utf-8")
    errors = gate.check(tree)
    joined = "\n".join(errors)
    assert "libQt6QuickTimeline.so.6" in joined
    assert "Qt6VirtualKeyboard.dll" in joined
    assert str(framework / "QtCharts") in joined
    assert "libQt6Widgets" not in joined


def test_bundle_gate_strip_removes_offenders_and_then_passes(tmp_path: Path) -> None:
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    lib = tree / "PySide6" / "Qt" / "lib"
    lib.mkdir(parents=True)
    (lib / "libQt6Widgets.so.6").write_text("", encoding="utf-8")
    (lib / "libQt6QuickTimeline.so.6").write_text("", encoding="utf-8")
    (tree / "libportaudio64bit-asio.dll").write_text("", encoding="utf-8")
    framework = tree / "QtCharts.framework" / "Versions" / "A"
    framework.mkdir(parents=True)
    (framework / "QtCharts").write_text("", encoding="utf-8")
    removed = gate.strip(tree)
    assert {path.name for path in removed} == {
        "libQt6QuickTimeline.so.6",
        "libportaudio64bit-asio.dll",
        "QtCharts",
    }
    assert (lib / "libQt6Widgets.so.6").is_file()
    assert not (tree / "QtCharts.framework").exists()
    assert gate.check(tree) == []


def test_bundle_gate_require_licenses_needs_the_verbatim_texts(tmp_path: Path) -> None:
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    licenses = tree / "THIRD_PARTY_LICENSES"
    licenses.mkdir(parents=True)
    (licenses / "INDEX.txt").write_text("unresolved: none\n", encoding="utf-8")
    errors = gate.check(tree, require_licenses=True)
    assert any("LGPL-3.0.txt" in item for item in errors)
    texts = licenses / "_texts"
    texts.mkdir()
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "PortAudio-LICENSE.txt"):
        (texts / name).write_text("x", encoding="utf-8")
    errors = gate.check(tree, require_licenses=True)
    assert errors == [
        "THIRD_PARTY_LICENSES/_notices/python.txt is missing",
        "THIRD_PARTY_LICENSES/_notices/qt-third-party.txt is missing",
    ]
    (licenses / "_notices").mkdir()
    for name in ("python.txt", "qt-third-party.txt"):
        (licenses / "_notices" / name).write_text("x", encoding="utf-8")
    assert gate.check(tree, require_licenses=True) == []


def test_installed_essentials_mode_ignores_wheel_stubs_and_stock_plugins(
    tmp_path: Path,
) -> None:
    gate = _load("check_bundle_contents")
    root = tmp_path / "PySide6"
    plugins = root / "Qt" / "plugins" / "platforminputcontexts"
    qml = root / "Qt" / "qml" / "QtQuick" / "Timeline"
    lib = root / "Qt" / "lib"
    plugins.mkdir(parents=True)
    qml.mkdir(parents=True)
    lib.mkdir(parents=True)
    (root / "QtCharts.pyi").write_text("", encoding="utf-8")
    (plugins / "libqtvirtualkeyboardplugin.so").write_text("", encoding="utf-8")
    (qml / "libqtquicktimelineplugin.so").write_text("", encoding="utf-8")
    # Essentials 6.9+ ships this versioned library although ReverbScope never loads it.
    (lib / "libQt6QuickTimeline.so.6").write_text("", encoding="utf-8")
    assert gate.check(root, installed_essentials=True) == []
    (root / "QtCharts.abi3.so").write_text("", encoding="utf-8")
    errors = gate.check(root, installed_essentials=True)
    assert any("QtCharts" in item for item in errors)


def test_bundle_gate_matches_gpl_qml_plugins_by_directory(tmp_path: Path) -> None:
    """#17: QML plugin names do not carry the module name; their directory does."""
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    qml = tree / "_internal" / "PySide6" / "Qt" / "qml" / "QtQuick"
    pinyin = qml / "VirtualKeyboard" / "Plugins" / "Pinyin"
    pinyin.mkdir(parents=True)
    (pinyin / "libqtvkbpinyinplugin.so").write_text("", encoding="utf-8")
    (qml / "VirtualKeyboard" / "qmldir").write_text("", encoding="utf-8")
    (qml / "VirtualKeyboard" / "libqtvkbplugin.so").write_text("", encoding="utf-8")
    timeline = qml / "Timeline"
    timeline.mkdir()
    (timeline / "qmldir").write_text("", encoding="utf-8")
    # The same module inside a macOS .app bundle.
    styles = tree / "ReverbScope.app" / "Contents" / "Resources" / "qml" / "QtQuick"
    styles = styles / "VirtualKeyboard" / "Styles"
    styles.mkdir(parents=True)
    (styles / "KeyboardStyle.qml").write_text("", encoding="utf-8")

    errors = gate.check(tree)
    joined = "\n".join(errors)
    assert "GPL-only Qt QML module present (QtVirtualKeyboard)" in joined
    assert str(pinyin / "libqtvkbpinyinplugin.so") in joined
    assert str(styles / "KeyboardStyle.qml") in joined
    assert "(QtQuickTimeline)" in joined

    removed = gate.strip(tree)
    assert {path.name for path in removed} == {
        "libqtvkbpinyinplugin.so",
        "libqtvkbplugin.so",
        "qmldir",
        "KeyboardStyle.qml",
    }
    # Stripping empties and removes the module directories up to (and
    # including) the now-empty qml/ directories, never the root itself.
    assert not (tree / "_internal" / "PySide6" / "Qt" / "qml").exists()
    assert not (tree / "ReverbScope.app" / "Contents" / "Resources" / "qml").exists()
    assert tree.is_dir()
    assert gate.check(tree) == []


def test_bundle_gate_rejects_any_qml_tree_in_a_frozen_bundle(tmp_path: Path) -> None:
    """#17: ReverbScope has no QML UI, so a collected QML tree means QtQml was imported."""
    gate = _load("check_bundle_contents")
    tree = tmp_path / "bundle"
    controls = tree / "_internal" / "PySide6" / "Qt" / "qml" / "QtQuick" / "Controls"
    controls.mkdir(parents=True)
    (controls / "libqtquickcontrols2plugin.so").write_text("", encoding="utf-8")
    (controls / "qmldir").write_text("", encoding="utf-8")
    # A file merely *named* qml is not a QML tree.
    (tree / "qml").write_text("", encoding="utf-8")

    errors = gate.check(tree)
    assert len(errors) == 1
    assert "QML tree present (2 files" in errors[0]
    assert errors[0].endswith(str(tree / "_internal" / "PySide6" / "Qt" / "qml"))
    # --strip removes GPL-only modules only; it must not hide a QML tree.
    assert gate.strip(tree) == []
    assert gate.check(tree) == errors
    # A PySide6 Essentials install legitimately carries the stock Qt/qml tree.
    assert gate.check(tree, installed_essentials=True) == []


def test_bundle_gate_strict_mode_covers_the_installed_essentials_qml_tree() -> None:
    """Every virtual-keyboard / timeline QML file of the real wheel is an offender."""
    import pytest

    gate = _load("check_bundle_contents")
    try:
        import PySide6
    except ImportError:
        pytest.skip("PySide6 is not installed")
    root = Path(next(iter(PySide6.__path__)))
    vkb = root / "Qt" / "qml" / "QtQuick" / "VirtualKeyboard"
    if not vkb.is_dir():
        pytest.skip("this PySide6 build ships no virtual-keyboard QML module")
    expected = {path for path in vkb.rglob("*") if path.is_file() and path.suffix != ".pyi"}
    assert expected
    reported = {path for path, _reason in gate.offending(root)}
    assert expected <= reported
    # The installed-Essentials mode keeps ignoring the stock tree.
    reported_installed = {path for path, _ in gate.offending(root, installed_essentials=True)}
    assert not (expected & reported_installed)


def test_license_bundle_carries_the_bundled_libsndfile_lgpl_text(tmp_path: Path) -> None:
    """soundfile's wheel bundles libsndfile (LGPL-2.1) and keeps its license text
    and source notes outside .dist-info, where the metadata scan did not look."""
    bundle_mod = _load("build_license_bundle")
    dest = tmp_path / "THIRD_PARTY_LICENSES"
    unresolved = bundle_mod.build(dest)
    found, missing = bundle_mod._package_license_files("soundfile")
    assert missing == [] and not [item for item in unresolved if item.startswith("soundfile:")]
    notice = (dest / "_notices" / "libsndfile.txt").read_text(encoding="utf-8")
    assert "LGPL" in notice or "Lesser General Public License" in notice
    if not found:  # soundfile built against a system libsndfile: nothing bundled
        return
    copying = (dest / "soundfile" / "_soundfile_data_COPYING").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in copying and "Version 2.1" in copying
    assert "soundfile/_soundfile_data_COPYING" in notice


def test_runtime_imports_of_the_bundles_have_licence_texts() -> None:
    """soundfile imports typing_extensions at run time; both editions froze it
    without its licence text."""
    module = _load("build_license_bundle")
    assert "typing-extensions" in module.REQUIRED
    assert "typing-extensions" in module.TERMINAL_REQUIRED


def test_the_licence_gate_needs_the_index(tmp_path: Path) -> None:
    gate = _load("check_bundle_contents")
    texts = tmp_path / "THIRD_PARTY_LICENSES" / "_texts"
    texts.mkdir(parents=True)
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "PortAudio-LICENSE.txt"):
        (texts / name).write_text("text", encoding="utf-8")
    errors = gate.check(tmp_path, require_licenses=True)
    assert "THIRD_PARTY_LICENSES/INDEX.txt is missing" in errors


def test_a_folder_above_the_bundle_is_not_a_qt_library(tmp_path: Path) -> None:
    """Parts of the absolute path were tested: a bundle under Qt6Projects/
    failed the Terminal Edition gate on every file."""
    gate = _load("check_bundle_contents")
    root = tmp_path / "Qt6Projects" / "reverbscope-terminal"
    (root / "_internal").mkdir(parents=True)
    (root / "_internal" / "_cffi_backend.so").write_bytes(b"\0")
    assert gate.gui_files(root) == []
    (root / "_internal" / "libQt6Core.so.6").write_bytes(b"\0")
    assert [what for _path, what in gate.gui_files(root)] == ["a Qt library"]


def test_both_editions_leave_the_developer_tools_out() -> None:
    """The desktop excludes named only the GPL Qt modules: pytest, setuptools,
    pygments and yaml were frozen into it."""
    spec = Path("packaging/reverbscope.spec").read_text(encoding="utf-8")
    dev = spec[
        spec.index("DEV_ONLY_EXCLUDES = [") : spec.index("]", spec.index("DEV_ONLY_EXCLUDES"))
    ]
    for module in ("setuptools", "pytest", "pygments", "yaml", "readline"):
        assert f'"{module}"' in dev, module
    desktop = spec[spec.index("    else [") :]
    assert desktop.split("]", 1)[0].count("*DEV_ONLY_EXCLUDES") == 1


def test_check_scripts_refuse_a_root_that_is_not_a_folder(tmp_path: Path) -> None:
    import pytest

    for name in ("check_src_safety", "check_doc_links"):
        with pytest.raises(SystemExit) as stop:
            _load(name).main(["--root", str(tmp_path / "missing")])
        assert stop.value.code == 2, name


def test_lock_names_are_read_from_any_specifier() -> None:
    lock = _load("compile_bundle_lock")
    assert lock._requirement_name("typing-extensions~=4.0") == "typing-extensions"
    assert lock._requirement_name("x===1") == "x"
    assert lock._requirement_name("name @ https://example.org/x.whl") == "name"
    assert lock._requirement_name("zope.interface (>=5)") == "zope.interface"


# --- Native libraries PyInstaller copies (R3-87) -----------------------------


def _frozen_tree(root: Path) -> Path:
    """A one-folder bundle: loose libraries, a wheel's own and Python modules."""
    internal = root / "_internal"
    (internal / "numpy.libs").mkdir(parents=True)
    (internal / "PySide6" / "Qt" / "lib").mkdir(parents=True)
    (internal / "python3.12" / "lib-dynload").mkdir(parents=True)
    (internal / "numpy.libs" / "libscipy_openblas64_.so").write_bytes(b"wheel")
    (internal / "PySide6" / "Qt" / "lib" / "libQt6Core.so.6").write_bytes(b"wheel")
    (internal / "libQt6Core.so.6").symlink_to(Path("PySide6/Qt/lib/libQt6Core.so.6"))
    (internal / "_cffi_backend.cpython-312-x86_64-linux-gnu.so").write_bytes(b"module")
    (internal / "python3.12" / "lib-dynload" / "_ssl.cpython-312-x86_64-linux-gnu.so").write_bytes(
        b"module"
    )
    (internal / "_ssl.pyd").write_bytes(b"module")
    (internal / "libmystery.so.2").write_bytes(b"from the build machine")
    (internal / "libssl-3.dll").write_bytes(b"from the Python installation")
    (internal / "python312.dll").write_bytes(b"the interpreter")
    (root / "reverbscope").write_bytes(b"executable")
    return root


def test_the_gate_finds_the_native_libraries_no_package_ships(tmp_path: Path) -> None:
    gate = _load("check_bundle_contents")
    root = _frozen_tree(tmp_path / "reverbscope")
    found = [path.relative_to(root).as_posix() for path in gate.loose_native_libraries(root)]
    assert found == [
        "_internal/libmystery.so.2",
        "_internal/libssl-3.dll",
        "_internal/python312.dll",
    ]


def test_the_licence_gate_fails_on_a_native_library_without_a_notice(tmp_path: Path) -> None:
    """GLib, libgcrypt, libsystemd, OpenSSL, libpython ... were copied from the
    build runner with no notice, and the gate still said 'bundle gate passed'."""
    gate = _load("check_bundle_contents")
    root = _frozen_tree(tmp_path / "reverbscope")
    licenses = root / "THIRD_PARTY_LICENSES"
    (licenses / "_texts").mkdir(parents=True)
    (licenses / "_notices" / "native").mkdir(parents=True)
    (licenses / "INDEX.txt").write_text("unresolved: none\n", encoding="utf-8")
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "PortAudio-LICENSE.txt"):
        (licenses / "_texts" / name).write_text("x", encoding="utf-8")
    for name in ("python.txt", "qt-third-party.txt"):
        (licenses / "_notices" / name).write_text("x", encoding="utf-8")
    errors = gate.check(root, require_licenses=True)
    assert len(errors) == 3
    assert all("native library without a licence notice" in error for error in errors)
    assert any(error.endswith("libmystery.so.2") for error in errors)
    (licenses / "NATIVE.txt").write_text(
        "header line\n"
        "libmystery.so.2\t_notices/native/mystery.txt\n"
        "libssl-3.dll\t_notices/native/openssl.txt\n"
        "python312.dll\t_notices/python.txt\n",
        encoding="utf-8",
    )
    (licenses / "_notices" / "native" / "openssl.txt").write_text("x", encoding="utf-8")
    assert gate.check(root, require_licenses=True) == [
        "THIRD_PARTY_LICENSES/_notices/native/mystery.txt (for libmystery.so.2) is missing"
    ]
    (licenses / "_notices" / "native" / "mystery.txt").write_text("x", encoding="utf-8")
    assert gate.check(root, require_licenses=True) == []


def test_native_libraries_of_a_python_installation_get_their_notices(
    tmp_path: Path, monkeypatch
) -> None:
    """Where no package database names a library (Windows, macOS), the
    libraries a Python installation brings get the notices in the repository."""
    bundle_mod = _load("build_license_bundle")
    monkeypatch.setattr(bundle_mod, "system_package", lambda library: None)
    root = _frozen_tree(tmp_path / "reverbscope")
    out = tmp_path / "THIRD_PARTY_LICENSES"
    unresolved = bundle_mod.build(out, frozen=root)
    assert [item for item in unresolved if item.startswith("native:")] == ["native:libmystery.so.2"]
    lines = (out / "NATIVE.txt").read_text(encoding="utf-8").splitlines()
    assert "libssl-3.dll\t_notices/native/openssl.txt" in lines
    assert "python312.dll\t_notices/python.txt" in lines
    openssl = (out / "_notices" / "native" / "openssl.txt").read_text(encoding="utf-8")
    assert "The OpenSSL Project Authors" in openssl and "Apache License" in openssl
    python = (out / "_notices" / "python.txt").read_text(encoding="utf-8")
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in python
    assert "native: 2 libraries outside Python packages" in (out / "INDEX.txt").read_text("utf-8")


def test_a_debian_library_gets_its_package_copyright_and_source(tmp_path: Path) -> None:
    """On the Ubuntu runner every library PyInstaller copied is credited to the
    package that installed it, with its copyright file and source package."""
    import shutil

    import pytest

    bundle_mod = _load("build_license_bundle")
    if shutil.which("dpkg-query") is None:
        pytest.skip("not a Debian or Ubuntu system")
    system_zlib = next(iter(bundle_mod._system_copies("libz.so.1")), None)
    if system_zlib is None:
        pytest.skip("no system zlib")
    root = tmp_path / "reverbscope"
    (root / "_internal").mkdir(parents=True)
    shutil.copyfile(system_zlib, root / "_internal" / "libz.so.1")
    (root / "_internal" / "libz-but-not.so.1").write_bytes(b"not the system's file")
    out = tmp_path / "THIRD_PARTY_LICENSES"
    notices, unresolved = bundle_mod.native_notices(out, root)
    assert unresolved == ["native:libz-but-not.so.1"]
    notice = out / notices["libz.so.1"]
    text = notice.read_text(encoding="utf-8")
    assert "libz.so.1" in text.splitlines()[0]
    assert "Source code: source package zlib" in text
    assert "Jean-loup Gailly" in text


def test_the_spec_drops_the_gtk_theme_and_only_the_libraries_it_alone_loads() -> None:
    """Qt's GTK3 platform theme pulled about thirty of the runner's libraries
    (GTK, Pango, Cairo, ATK, mostly LGPL) into the Linux bundle."""
    import importlib.util

    path = Path("packaging") / "pyinstaller_filters.py"
    spec = importlib.util.spec_from_file_location("pyinstaller_filters", path)
    assert spec is not None and spec.loader is not None
    filters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(filters)
    loads = {
        "/qt/plugins/platformthemes/libqgtk3.so": {
            "libgtk-3.so.0",
            "libpango-1.0.so.0",
            "libglib-2.0.so.0",
            "libQt6Core.so.6",
        },
        "/usr/lib/libgtk-3.so.0": {"libpango-1.0.so.0", "libglib-2.0.so.0"},
        "/usr/lib/libpango-1.0.so.0": {"libglib-2.0.so.0"},
        "/usr/lib/libglib-2.0.so.0": set(),
        "/qt/lib/libQt6Core.so.6": {"libglib-2.0.so.0"},
        "/qt/plugins/platforms/libqxcb.so": {"libQt6Core.so.6", "libglib-2.0.so.0"},
    }
    binaries = [
        (
            "PySide6/Qt/plugins/platformthemes/libqgtk3.so",
            "/qt/plugins/platformthemes/libqgtk3.so",
            "BINARY",
        ),
        ("libgtk-3.so.0", "/usr/lib/libgtk-3.so.0", "BINARY"),
        ("libpango-1.0.so.0", "/usr/lib/libpango-1.0.so.0", "BINARY"),
        ("libglib-2.0.so.0", "/usr/lib/libglib-2.0.so.0", "BINARY"),
        ("PySide6/Qt/lib/libQt6Core.so.6", "/qt/lib/libQt6Core.so.6", "BINARY"),
        ("PySide6/Qt/plugins/platforms/libqxcb.so", "/qt/plugins/platforms/libqxcb.so", "BINARY"),
    ]
    kept = filters.without_plugin(binaries, "platformthemes/libqgtk3.so", loads.__getitem__)
    # QtCore links GLib, so GLib stays; GTK and Pango go with the theme.
    assert [entry[0] for entry in kept] == [
        "libglib-2.0.so.0",
        "PySide6/Qt/lib/libQt6Core.so.6",
        "PySide6/Qt/plugins/platforms/libqxcb.so",
    ]
    assert filters.without_plugin(kept, "platformthemes/libqgtk3.so", loads.__getitem__) == kept
    spec_text = Path("packaging/reverbscope.spec").read_text(encoding="utf-8")
    assert 'without_plugin(a.binaries, "platformthemes/libqgtk3.so"' in spec_text


def test_the_qt_third_party_notice_matches_the_pinned_qt() -> None:
    """DEPENDENCIES.md §4: the bundle must carry the notices of the code inside
    Qt (PCRE2, HarfBuzz, libpng, MD4C, the Unicode data, ...). The file is
    generated for one Qt version; a new PySide6 pin needs a new file."""
    notice = Path("packaging/licenses/qt-third-party.txt").read_text(encoding="utf-8")
    lock = Path("requirements/bundle.lock").read_text(encoding="utf-8")
    pinned = next(
        line.split("==", 1)[1].split()[0]
        for line in lock.splitlines()
        if line.lower().startswith("pyside6-essentials==")
        or line.lower().startswith("pyside6_essentials==")
    )
    assert notice.splitlines()[0] == f"Third-party code inside Qt {pinned}"
    for name in ("PCRE2", "HarfBuzz", "libpng", "libjpeg", "MD4C", "Unicode Character Database"):
        assert name in notice, name
    assert "--- ICU " in notice and "--- FTL ---" in notice


def test_the_qt_notice_lists_shipped_code_with_the_chosen_licence_texts(tmp_path: Path) -> None:
    import json

    generator = _load("qt_third_party_notice")
    qtbase = tmp_path / "qtbase"
    (qtbase / "LICENSES").mkdir(parents=True)
    for licence in ("FTL", "GPL-2.0-only", "MIT", "BSD-3-Clause"):
        (qtbase / "LICENSES" / f"{licence}.txt").write_text(f"{licence} text", "utf-8")
    entries = [
        {
            "Id": "freetype",
            "Name": "Freetype 2",
            "QDocModule": "qtgui",
            "QtUsage": "Used in Qt GUI.",
            "Version": "2.14.3",
            "LicenseId": "FTL OR GPL-2.0-only",
            "Copyright": ["Copyright (c) David Turner"],
            "DownloadLocation": "https://download.savannah.gnu.org/releases/freetype/",
        },
        {
            "Id": "md4c",
            "Name": "MD4C",
            "QDocModule": "qtgui",
            "QtUsage": "Optionally used in QTextDocument.",
            "LicenseId": "MIT",
            "Copyright": "Copyright © 2016-2024 Martin Mitáš",
        },
        {
            "Id": "kwin",
            "Name": "KWin",
            "QDocModule": "qtcore",
            "QtUsage": "Used as part of the build system.",
            "LicenseId": "BSD-3-Clause",
        },
        {
            "Id": "sqlite",
            "Name": "SQLite",
            "QDocModule": "qtsql",
            "QtUsage": "Used in Qt SQL Lite plugin.",
            "LicenseId": "blessing",
        },
        {
            "Id": "presentation-time",
            "Name": "Wayland presentation time",
            "QDocModule": "qtwaylandcompositor",
            "QtUsage": "Used in the Qt Wayland Compositor",
            "LicenseId": "MIT",
        },
    ]
    (qtbase / "src").mkdir()
    (qtbase / "src" / "qt_attribution.json").write_text(json.dumps(entries), encoding="utf-8")
    icu = tmp_path / "ICU-LICENSE"
    icu.write_text("UNICODE LICENSE", encoding="utf-8")
    text, missing = generator.render("6.11.2", [qtbase], icu, "73.2")
    assert missing == []
    assert text.splitlines()[0] == "Third-party code inside Qt 6.11.2"
    assert "Freetype 2 2.14.3" in text and "MD4C" in text and "Martin Mitáš" in text
    assert "KWin" not in text and "SQLite" not in text and "presentation" not in text
    # Of "FTL OR GPL-2.0-only" the FreeType licence is the one ReverbScope uses.
    assert "--- FTL ---" in text and "GPL-2.0-only text" not in text
    assert "--- ICU 73.2 ---" in text and "UNICODE LICENSE" in text
