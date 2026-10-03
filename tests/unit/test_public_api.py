"""Tier 1 public API lock and version agreement."""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import reverbscope
from reverbscope import TIER1_EXPORTS


def _architecture_tier1_names() -> set[str]:
    text = Path("docs/ARCHITECTURE_V1.md").read_text(encoding="utf-8")
    match = re.search(r"```python\n(__version__.*?)\n```", text, flags=re.S)
    assert match is not None, "Tier 1 export block missing from ARCHITECTURE_V1.md"
    cleaned = "\n".join(line.split("#", 1)[0] for line in match.group(1).splitlines())
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned))
    names.discard("and")
    names.discard("its")
    names.discard("subclasses")
    error_names = {
        "ReverbScopeError",
        "ConfigurationError",
        "InvalidAudioError",
        "SampleRateMismatchError",
        "AnalysisError",
        "InsufficientDataError",
        "AudioDeviceError",
        "AudioBackendUnavailableError",
        "SessionError",
    }
    names |= error_names
    return names


def test_tier1_exports_match_architecture_document() -> None:
    documented = _architecture_tier1_names()
    exported = set(TIER1_EXPORTS)
    assert exported == documented, (
        f"only in __init__.py: {sorted(exported - documented)}; "
        f"only in ARCHITECTURE_V1.md: {sorted(documented - exported)}"
    )


def test_tier1_names_are_importable() -> None:
    for name in TIER1_EXPORTS:
        assert hasattr(reverbscope, name), name
        getattr(reverbscope, name)


def test_import_reverbscope_does_not_import_scipy() -> None:
    # A fresh interpreter is not available here; the contract is that
    # ``import reverbscope`` itself does not pull SciPy. The lazy map must not
    # list reverbscope.core at module level besides the mapping strings.
    source = Path("src/reverbscope/__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert all("scipy" not in name and "PySide6" not in name for name in imported)
    assert "reverbscope.core" not in imported
    assert "reverbscope.ui" not in imported


def test_version_matches_pyproject() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, flags=re.M)
    assert match is not None
    assert reverbscope.__version__ == match.group(1)
    importlib.reload(reverbscope)
    assert reverbscope.__version__ == match.group(1)
