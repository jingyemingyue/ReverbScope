"""Refuse network imports and shell-outs under ``src/`` (ARCHITECTURE_V1.md §2, §8).

Names are resolved through each module's own import statements, so an import
alias does not hide a call: ``import numpy as np; np.load(...)`` is
``numpy.load`` and ``from os import system as run; run(...)`` is
``os.system``. Importing a banned function by name (``from os import system``)
is reported even if it is never called, and so is a star import from a module
that has banned functions. ``importlib.import_module("subprocess")`` and
``__import__("subprocess")`` count as the plain import; a dynamic import of a
computed name cannot be checked and is reported unless its file is listed in
``ALLOWED_DYNAMIC_IMPORTS`` with a reason (#16).

This is a lint for honest code, not a sandbox: a name rebound at run time
(``load = getattr(np, "lo" + "ad")``) is not followed, and a local variable
that happens to share an import alias is treated as the import.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BANNED_MODULES = frozenset(
    {"socket", "urllib", "http", "requests", "ssl", "subprocess", "pickle", "pty", "ftplib"}
)
BANNED_CALLS = frozenset(
    {
        "eval",
        "exec",
        "builtins.eval",
        "builtins.exec",
        "os.system",
        "os.popen",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.startfile",
        "os.fork",
        "os.forkpty",
        "pickle.loads",
        "pickle.load",
        "numpy.load",
        "numpy.lib.npyio.load",
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
    }
)
#: ``os.execv``, ``os.spawnlp`` and the rest of those families.
BANNED_CALL_PREFIXES = ("os.exec", "os.spawn")
#: Modules whose ``import *`` would bring a banned function in unnamed.
STAR_IMPORT_BANNED = frozenset({"os", "numpy", "numpy.lib.npyio", "asyncio", "builtins"})
DYNAMIC_IMPORT_CALLS = frozenset(
    {"importlib.import_module", "importlib.__import__", "__import__", "builtins.__import__"}
)
#: Files that may import a computed module name (path relative to the
#: scanned root or to its parent), with the reason.
ALLOWED_DYNAMIC_IMPORTS = {
    "reverbscope/__init__.py": (
        "lazy public API: the module names come from the fixed _LAZY table, "
        "which lists reverbscope modules only"
    ),
}


def _dynamic_import_allowed(path: Path, root: Path) -> bool:
    relative = path.relative_to(root).as_posix()
    return relative in ALLOWED_DYNAMIC_IMPORTS or (
        f"{root.name}/{relative}" in ALLOWED_DYNAMIC_IMPORTS
    )


def _is_banned_call(name: str) -> bool:
    return name in BANNED_CALLS or name.startswith(BANNED_CALL_PREFIXES)


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local name -> fully qualified name, from every import in the module."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    table[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    table[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if alias.name != "*":
                    table[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return table


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else ""
    return ""


def _qualified(node: ast.AST, aliases: dict[str, str]) -> str:
    """Qualified name of a call target with the leading alias resolved."""
    dotted = _dotted(node)
    if not dotted:
        return ""
    head, _, rest = dotted.partition(".")
    resolved = aliases.get(head, head)
    return f"{resolved}.{rest}" if rest else resolved


def _string_argument(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for keyword in call.keywords:
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            return value if isinstance(value, str) else None
    return None


def _check_file(path: Path, root: Path) -> list[str]:
    bad: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module.split(".")[0]]
            for alias in node.names:
                imported = f"{node.module}.{alias.name}"
                if _is_banned_call(imported) or (
                    alias.name == "*" and node.module in STAR_IMPORT_BANNED
                ):
                    bad.append(f"{path}:{node.lineno}: from {node.module} import {alias.name}")
        hits = [name for name in names if name in BANNED_MODULES]
        if hits:
            bad.append(f"{path}:{node.lineno}: import {hits}")
        if not isinstance(node, ast.Call):
            continue
        called = _qualified(node.func, aliases)
        if _is_banned_call(called):
            bad.append(f"{path}:{node.lineno}: {called}")
        if called in DYNAMIC_IMPORT_CALLS:
            target = _string_argument(node)
            if target is None:
                if not _dynamic_import_allowed(path, root):
                    bad.append(f"{path}:{node.lineno}: {called} of a computed module name")
            elif target.split(".")[0] in BANNED_MODULES:
                bad.append(f"{path}:{node.lineno}: {called}({target!r})")
        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                bad.append(f"{path}:{node.lineno}: shell=True")
            if (
                keyword.arg == "allow_pickle"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                bad.append(f"{path}:{node.lineno}: allow_pickle=True")
    return bad


def check(root: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(root.rglob("*.py")):
        bad.extend(_check_file(path, root))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("src"), help="Python tree to scan")
    args = parser.parse_args(argv)
    errors = check(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"src safety ok under {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
