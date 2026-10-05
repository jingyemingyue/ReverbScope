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
        assert missing == {"text:LGPL-3.0.txt", "text:GPL-3.0.txt"}
    else:
        assert missing == set()


def test_macos_info_plist_declares_microphone() -> None:
    plist = Path("packaging/macos/Info.plist").read_text(encoding="utf-8")
    assert "NSMicrophoneUsageDescription" in plist
    assert "measurement microphone" in plist
    entitlements = Path("packaging/macos/entitlements.plist").read_text(encoding="utf-8")
    assert "com.apple.security.device.audio-input" in entitlements
    spec = Path("packaging/roomscope.spec").read_text(encoding="utf-8")
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
    # Essentials 6.9+ ships this versioned library although RoomScope never loads it.
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
    styles = tree / "RoomScope.app" / "Contents" / "Resources" / "qml" / "QtQuick"
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
    assert not (tree / "RoomScope.app" / "Contents" / "Resources" / "qml").exists()
    assert tree.is_dir()
    assert gate.check(tree) == []


def test_bundle_gate_rejects_any_qml_tree_in_a_frozen_bundle(tmp_path: Path) -> None:
    """#17: RoomScope has no QML UI, so a collected QML tree means QtQml was imported."""
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
    root = tmp_path / "Qt6Projects" / "roomscope-terminal"
    (root / "_internal").mkdir(parents=True)
    (root / "_internal" / "_cffi_backend.so").write_bytes(b"\0")
    assert gate.gui_files(root) == []
    (root / "_internal" / "libQt6Core.so.6").write_bytes(b"\0")
    assert [what for _path, what in gate.gui_files(root)] == ["a Qt library"]


def test_both_editions_leave_the_developer_tools_out() -> None:
    """The desktop excludes named only the GPL Qt modules: pytest, setuptools,
    pygments and yaml were frozen into it."""
    spec = Path("packaging/roomscope.spec").read_text(encoding="utf-8")
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
