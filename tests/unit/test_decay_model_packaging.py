"""The opt-in model is available in an installed wheel and both frozen editions."""

from __future__ import annotations

import hashlib
import runpy
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hatchling.build import build_wheel

ROOT = Path(__file__).resolve().parents[2]
RESOURCE = "roomscope/model_data/decay_initializer_v1.json"
SHIPPED_SHA256 = "2ba0004247ce90ff70e92fb0e97ae14f59d12d92e6029732224c853fecc12234"


def test_built_wheel_contains_the_exact_local_model(tmp_path: Path) -> None:
    name = build_wheel(str(tmp_path))
    with zipfile.ZipFile(tmp_path / name) as wheel:
        model = wheel.read(RESOURCE)
        assert model == (ROOT / "src" / RESOURCE).read_bytes()
        assert hashlib.sha256(model).hexdigest() == SHIPPED_SHA256


@pytest.mark.parametrize("edition", ["desktop", "terminal"])
def test_frozen_editions_collect_the_local_model_without_audio_or_building_a_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edition: str
) -> None:
    monkeypatch.setenv("ROOMSCOPE_PACKAGE", edition)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(sys, "platform", "linux")

    def analysis(*args: object, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=kwargs["datas"])

    def collect(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace()

    spec = runpy.run_path(
        str(ROOT / "packaging" / "roomscope.spec"),
        init_globals={
            "SPECPATH": str(ROOT / "packaging"),
            "workpath": str(tmp_path),
            "Analysis": analysis,
            "PYZ": collect,
            "EXE": collect,
            "COLLECT": collect,
        },
    )
    collected = {
        f"{destination}/{Path(source).name}": Path(source).read_bytes()
        for source, destination in spec["a"].datas
        if Path(source).is_file()
    }
    assert collected[RESOURCE] == (ROOT / "src" / RESOURCE).read_bytes()
