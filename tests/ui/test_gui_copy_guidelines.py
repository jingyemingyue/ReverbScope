"""GUI copy must follow guidelines §16.2 / §16.4 Phase 0: no docs paths,
CLI command names, bilingual restart hints, or ALL-CAPS section msgids in
user-visible gettext strings."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI = Path("src/reverbscope/ui")
FORBIDDEN_IN_MSGID = (
    "docs/",
    "reverbscope analyze",
    "reverbscope compare",
    "session.json",
    "comparison.json",
)


def _msgid_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name not in {"_", "N_", "pgettext", "npgettext"}:
            continue
        args = list(node.args)
        if name in {"pgettext", "npgettext"} and args:
            args = args[1:]
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append((getattr(node, "lineno", 0), arg.value))
            elif isinstance(arg, ast.JoinedStr):
                parts: list[str] = []
                for value in arg.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        parts.append(value.value)
                    else:
                        parts.append("{}")
                out.append((getattr(node, "lineno", 0), "".join(parts)))
    return out


def _is_filter_msgid(text: str) -> bool:
    """File-dialog filters may name extensions (§16.2)."""
    return ";;" in text or text.startswith("Session files (")


def test_ui_msgids_have_no_docs_paths_or_cli_commands() -> None:
    violations: list[str] = []
    for path in sorted(UI.rglob("*.py")):
        for line, text in _msgid_literals(path):
            if _is_filter_msgid(text):
                continue
            for needle in FORBIDDEN_IN_MSGID:
                if needle in text:
                    violations.append(f"{path}:{line}: {needle!r} in {text!r}")
    assert violations == [], "§16.2 GUI copy:\n" + "\n".join(violations)


def test_settings_restart_hint_is_single_language() -> None:
    from reverbscope.ui import settings_dialog as module

    text = module.RESTART_FOR_LANGUAGE
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    has_english = "language change" in text.lower() or "restarts" in text.lower()
    assert not (has_cjk and has_english), text
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "_(RESTART_FOR_LANGUAGE)" in source


def test_profile_dialog_copy_avoids_docs_and_all_caps_sections() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel

    from reverbscope.ui.profile_dialog import ProfileDialog

    app = QApplication.instance() or QApplication([])
    dialog = ProfileDialog("generic")
    labels = [widget.text() for widget in dialog.findChildren(QLabel)]
    assert "WHAT IT WATCHES FOR" not in labels
    assert "WHAT IT DOES NOT JUDGE" not in labels
    assert any(text == "What it watches for" for text in labels), labels
    assert not any("docs/" in text for text in labels), labels
    dialog.close()
    del app
