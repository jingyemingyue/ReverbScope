from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_installed_wheels_match_the_bundle_gate() -> None:
    """Installed-wheel layout differs by OS (DEPENDENCIES.md §6)."""
    module = _load("audit_wheel_contents", Path("scripts") / "audit_wheel_contents.py")
    reports = {item.name: item for item in module.audit_required()}
    numpy = reports["numpy"]
    scipy = reports["scipy"]
    soundfile = reports["soundfile"]
    sounddevice = reports["sounddevice"]
    matplotlib = reports["matplotlib"]
    numpy_libs = module.bundled_shared_libs(numpy)
    soundfile_libs = module.bundled_shared_libs(soundfile)
    numpy_openblas = (*numpy_libs, *numpy.natives)
    snd_libs = (*soundfile_libs, *soundfile.natives)

    assert matplotlib.ttconv == ()
    assert not any("ttconv" in name.lower() for name in matplotlib.natives)
    assert any("qhull" in name.lower() for name in scipy.licenses)
    assert any("libsndfile" in name.lower() for name in snd_libs)

    has_openblas = any("openblas" in name.lower() for name in numpy_openblas)
    has_quadmath = any("quadmath" in name.lower() for name in numpy_openblas)

    if sys.platform.startswith("linux"):
        assert has_openblas and has_quadmath
        assert sounddevice.asio == ()
    elif sys.platform == "win32":
        assert has_openblas and not has_quadmath
        assert sounddevice.asio
    else:
        # macOS: numpy's macosx_14_0 wheels (what macos-latest installs) link
        # Apple Accelerate and bundle no shared library at all; the older
        # macosx_11_0 / 10_13 wheels bundle OpenBLAS together with the GCC
        # runtime (libgfortran, libquadmath, libgcc_s) under numpy/.dylibs/.
        # Either layout is acceptable; a wheel with OpenBLAS but without the
        # GCC runtime (or vice versa) would be a new layout to audit.
        assert has_openblas == has_quadmath
        if has_openblas:
            assert any(".dylibs/" in name for name in numpy_libs)


def test_bundled_shared_libs_recognises_macos_dylibs() -> None:
    module = _load("audit_wheel_contents_dylibs", Path("scripts") / "audit_wheel_contents.py")
    audit = module.PackageAudit(
        name="numpy",
        version="2.5.3",
        natives=("numpy/.dylibs/libscipy_openblas64_.dylib",),
        licenses=(),
        asio=(),
        ttconv=(),
    )
    libs = module.bundled_shared_libs(audit)
    assert any("openblas" in name.lower() for name in libs)


def test_src_safety_script_is_clean() -> None:
    module = _load("check_src_safety", Path("scripts") / "check_src_safety.py")
    assert module.check(Path("src")) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import numpy as np\nnp.load('x.npy')\n", "numpy.load"),
        ("from numpy import load\nload('x.npy')\n", "from numpy import load"),
        ("from os import system\n", "from os import system"),
        ("from os import system as run\nrun('ls')\n", "os.system"),
        ("import os as o\no.popen('ls')\n", "os.popen"),
        ("import os\nos.execv('/bin/sh', ['sh'])\n", "os.execv"),
        ("import os\nos.spawnlp(0, 'sh', 'sh')\n", "os.spawnlp"),
        ("import importlib\nimportlib.import_module('subprocess')\n", "'subprocess'"),
        ("from importlib import import_module\nimport_module('socket')\n", "'socket'"),
        ("__import__('subprocess')\n", "__import__('subprocess')"),
        ("import importlib\nname = 'x'\nimportlib.import_module(name)\n", "computed"),
        ("eval('1 + 1')\n", "eval"),
        ("import pickle as p\n", "import ['pickle']"),
        ("import numpy as np\nnp.load('x.npy', allow_pickle=True)\n", "allow_pickle=True"),
        ("from os import *\nsystem('ls')\n", "from os import *"),
        ("import importlib\nimportlib.__import__('subprocess')\n", "'subprocess'"),
        ("import numpy\nnumpy.lib.npyio.load('x.npy')\n", "numpy.lib.npyio.load"),
        ("import asyncio\nasyncio.create_subprocess_shell('ls')\n", "create_subprocess_shell"),
        ("import pty\n", "import ['pty']"),
        ("import os\nos.fork()\n", "os.fork"),
    ],
)
def test_src_safety_catches_aliases_and_dynamic_imports(
    tmp_path: Path, source: str, expected: str
) -> None:
    """#16: every pattern is reported from a scratch tree."""
    module = _load("check_src_safety", Path("scripts") / "check_src_safety.py")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "bad.py").write_text(source, encoding="utf-8")
    found = module.check(tmp_path)
    assert found, source
    assert any(expected in item for item in found), found


def test_src_safety_leaves_look_alikes_alone(tmp_path: Path) -> None:
    module = _load("check_src_safety", Path("scripts") / "check_src_safety.py")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "fine.py").write_text(
        "import numpy as np\n"
        "np.loadtxt('x.txt')\n"
        "class Model:\n"
        "    def eval(self):\n"
        "        return 1\n"
        "Model().eval()\n"
        "import importlib\n"
        "importlib.import_module('json')\n",
        encoding="utf-8",
    )
    # The one computed import RoomScope makes is allowed by file, with a reason,
    # whether the scan starts at src/ or at src/roomscope/.
    (tmp_path / "roomscope").mkdir()
    (tmp_path / "roomscope" / "__init__.py").write_text(
        "from importlib import import_module\nname = 'roomscope.core'\nimport_module(name)\n",
        encoding="utf-8",
    )
    assert module.check(tmp_path) == []
    assert module.check(tmp_path / "roomscope") == []
    # The allowance is for that file only, not for any __init__.py below it.
    nested = tmp_path / "pkg" / "roomscope"
    nested.mkdir(parents=True)
    (nested / "__init__.py").write_text(
        "from importlib import import_module\nimport_module(name)\n", encoding="utf-8"
    )
    assert any("computed" in item for item in module.check(tmp_path))


def test_inno_setup_and_linux_desktop_files_exist() -> None:
    iss = Path("packaging/windows/roomscope.iss").read_text(encoding="utf-8")
    assert "roomscope.exe" in iss
    assert "dist\\roomscope" in iss or "dist/roomscope" in iss
    # Shortcuts start the windowed launcher, which opens the GUI without
    # arguments; the console roomscope.exe would only print CLI help.
    assert '#define MyAppExeName "roomscope-gui.exe"' in iss
    assert 'Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"' in iss
    assert "OutputDir=..\\..\\dist" in iss
    desktop = Path("packaging/linux/roomscope.desktop").read_text(encoding="utf-8")
    assert "Exec=roomscope-gui" in desktop
    apprun = Path("packaging/linux/AppRun").read_text(encoding="utf-8")
    assert '"$HERE/roomscope-gui"' in apprun
    assert '"$HERE/roomscope" "$@"' in apprun
    spec = Path("packaging/roomscope.spec").read_text(encoding="utf-8")
    assert 'name="roomscope-gui"' in spec
    dmg = Path("packaging/macos/make_dmg.sh").read_text(encoding="utf-8")
    assert "hdiutil" in dmg


def test_smoke_bundle_finds_explicit_binary(tmp_path: Path) -> None:
    module = _load("smoke_bundle", Path("scripts") / "smoke_bundle.py")
    fake = tmp_path / "roomscope"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    assert module.find_binary(tmp_path, None) == fake
    assert module.find_binary(None, fake) == fake
    assert module.smoke_gui_argv(fake) == [str(fake), "gui", "--smoke"]
    assert module.find_gui_launcher(fake) is None
    launcher = tmp_path / "roomscope-gui.exe"
    launcher.write_text("", encoding="utf-8")
    # A pip install's roomscope-gui script ignores "gui --smoke": not a launcher.
    assert module.find_gui_launcher(fake) is None
    (tmp_path / "_internal").mkdir()
    assert module.find_gui_launcher(fake) == launcher


def test_settings_refuse_deep_json_and_fall_back(tmp_path: Path, monkeypatch) -> None:
    from roomscope.io.jsonutil import MAX_JSON_DEPTH
    from roomscope.settings import load_settings, settings_path

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    depth = MAX_JSON_DEPTH + 3
    settings_path().write_text("{" * depth + "}" * depth, encoding="utf-8")
    loaded = load_settings()
    assert loaded.language == ""
    assert loaded.copy_recording is True


def test_desktop_launch_check_requires_a_running_gui() -> None:
    module = _load("smoke_bundle_launch", Path("scripts") / "smoke_bundle.py")
    env = dict(os.environ)
    stays = [sys.executable, "-c", "import time; time.sleep(30)"]
    module.check_stays_open(stays, env, seconds=0.5)
    exits = [sys.executable, "-c", "raise SystemExit(2)"]
    with pytest.raises(SystemExit, match="exited at once"):
        module.check_stays_open(exits, env, seconds=3.0)


def test_smoke_checks_the_doctor_report(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import subprocess

    module = _load("smoke_bundle_doctor", Path("scripts") / "smoke_bundle.py")
    report: dict[str, Any] = {
        "packages": {"numpy": "2.3.0", "scipy": "1.16.0"},
        "build": {"commit": "abc"},
        "audio_callbacks": "ok",
    }

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert argv[1:] == ["--backend", "fake", "doctor", "--json"]
        return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.check_doctor(Path("roomscope"), "abc") == report
    with pytest.raises(SystemExit, match="expected 'def'"):
        module.check_doctor(Path("roomscope"), "def")
    report["audio_callbacks"] = "failed: MemoryError()"
    with pytest.raises(SystemExit, match="audio callbacks"):
        module.check_doctor(Path("roomscope"))
    report["audio_callbacks"] = "ok"
    report["packages"]["scipy"] = None
    with pytest.raises(SystemExit, match="no version for: scipy"):
        module.check_doctor(Path("roomscope"))
