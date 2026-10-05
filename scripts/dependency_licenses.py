"""Print the license metadata of every installed package ReverbScope depends on.

    python scripts/dependency_licenses.py

Used to keep docs/DEPENDENCIES.md in sync with the installed versions. It
reads the installed package metadata (License-Expression / License /
classifiers) and lists the license files shipped in each dist-info. PyPI
metadata is only a starting point: the upstream LICENSE file is authoritative.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distribution

PACKAGES = [
    "numpy",
    "scipy",
    "soundfile",
    "sounddevice",
    "matplotlib",
    "PySide6_Essentials",
    "shiboken6",
    "cffi",
    "pycparser",
    "contourpy",
    "cycler",
    "fonttools",
    "kiwisolver",
    "packaging",
    "pillow",
    "pyparsing",
    "python-dateutil",
    "six",
    "typing-extensions",
    "pytest",
    "pytest-cov",
    "ruff",
    "mypy",
]


def main() -> None:
    print(f"{'package':18s} {'version':12s} {'license (metadata)':45s} license files in dist-info")
    for name in PACKAGES:
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            print(f"{name:18s} (not installed)")
            continue
        meta = dist.metadata
        expression = meta.get("License-Expression") or ""
        license_field = (meta.get("License") or "").splitlines()[0] if meta.get("License") else ""
        classifiers = [
            c.split("::")[-1].strip()
            for c in meta.get_all("Classifier") or []
            if c.startswith("License")
        ]
        summary = expression or license_field or "; ".join(classifiers) or "UNKNOWN / NEEDS REVIEW"
        files = [
            f.name
            for f in (dist.files or [])
            if f.parent.name.endswith(".dist-info")
            and any(
                token in f.name.upper() for token in ("LICENSE", "LICENCE", "COPYING", "NOTICE")
            )
        ]
        print(f"{name:18s} {dist.version:12s} {summary[:45]:45s} {', '.join(files) or '-'}")


if __name__ == "__main__":
    main()
