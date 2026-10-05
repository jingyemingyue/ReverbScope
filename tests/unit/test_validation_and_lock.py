from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import ModuleType

import pytest


def _load_lock_script():
    path = Path("scripts") / "compile_bundle_lock.py"
    spec = importlib.util.spec_from_file_location("compile_bundle_lock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_protocol_states_tolerances_before_results() -> None:
    text = Path("docs/VALIDATION.md").read_text(encoding="utf-8")
    assert "protocol written; not yet run" in text.lower()
    assert "5 % or 0.02 s" in text
    assert "0.2 ms" in text
    assert "1.0 dB" in text
    assert "5 cm" in text
    assert "Same WAV" in text
    assert "| Room | Position | Take |" in text
    assert "Nothing below is filled from the fake backend" in text


def test_bundle_lock_is_runtime_only() -> None:
    lock = Path("requirements/bundle.lock").read_text(encoding="utf-8")
    assert "numpy==" in lock
    assert "scipy==" in lock
    assert "matplotlib==" in lock
    lowered = lock.lower()
    for forbidden in ("mypy==", "pytest==", "ruff==", "coverage=="):
        assert forbidden not in lowered
    compiled = _load_lock_script().compile_lock()
    names = {line.split("==", 1)[0].lower().replace("_", "-") for line in compiled}
    assert "numpy" in names
    assert "mypy" not in names


class _FakeDistribution:
    def __init__(self, name: str) -> None:
        self.metadata = {"Name": name}
        self.version = "1.0"


def _fake_graph(
    monkeypatch: pytest.MonkeyPatch, graph: dict[str, list[str]], missing: str = ""
) -> ModuleType:
    module = _load_lock_script()

    def distribution(name: str) -> _FakeDistribution:
        if name == missing:
            raise PackageNotFoundError(name)
        return _FakeDistribution(name)

    monkeypatch.setattr(module, "distribution", distribution)
    monkeypatch.setattr(module, "requires", lambda name: graph.get(name, []))
    return module


def test_the_lock_skips_extras_but_keeps_dependencies_named_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extra-marker check ran on the whole requirement, so a dependency
    such as "foo-extra==1.0" was left out of the lock."""
    module = _fake_graph(
        monkeypatch,
        {
            "top": [
                "foo-extra==1.0",
                "zope.extra>=2",
                'bar; extra == "test"',
                'baz; python_version >= "3.8" and extra=="doc"',
            ]
        },
    )
    seen: dict[str, str] = {}
    module._walk("top", seen)
    assert sorted(seen) == ["foo-extra", "top", "zope.extra"]


def test_a_missing_runtime_package_is_refused_before_the_lock_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the gui extra the lock was rewritten without Qt, so the
    bundle installed whatever Qt was newest."""
    module = _fake_graph(monkeypatch, {}, missing="PySide6_Essentials")
    out = tmp_path / "bundle.lock"
    with pytest.raises(SystemExit, match="not installed: PySide6_Essentials;"):
        module.main(["--out", str(out)])
    assert not out.exists()
