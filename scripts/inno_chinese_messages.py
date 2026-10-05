"""Simplified Chinese messages for the Windows installer (Inno Setup).

Released Inno Setup versions up to 6.7 keep ``ChineseSimplified.isl`` among
the unofficial translations (``Files/Languages/Unofficial`` in the Inno Setup
repository), which their installer does not install; the development branch
has since made it an official translation. This script prints the path of the
file ``packaging/windows/reverbscope.iss`` should use:

* the compiler's own ``Languages/ChineseSimplified.isl`` when it has one;
* otherwise the file from the Inno Setup repository at the release tag that
  matches the compiler used by the release workflow, downloaded once and
  checked against its SHA-256 (a changed file stops the build).

Usage: ``python scripts/inno_chinese_messages.py --iscc <ISCC.exe> --out <dir>``;
pass the printed path to ISCC as ``/DChineseMessages=<path>``.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

TAG = "is-6_7_1"
URL = (
    "https://raw.githubusercontent.com/jrsoftware/issrc/"
    f"{TAG}/Files/Languages/Unofficial/ChineseSimplified.isl"
)
SHA256 = "7d544b9bb1d142cfa11f2e5d3cc8abe2e55f8e066c5124e3772675aa236e1278"
FILENAME = "ChineseSimplified.isl"


def bundled(iscc: Path) -> Path | None:
    """The compiler's own copy, if this Inno Setup ships it as official."""
    candidate = iscc.parent / "Languages" / FILENAME
    return candidate if candidate.is_file() else None


def verified(data: bytes) -> bytes:
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"{FILENAME} from {URL} has SHA-256 {digest}, expected {SHA256}")
    return data


def messages_path(iscc: Path, out: Path) -> Path:
    own = bundled(iscc)
    if own is not None:
        return own
    target = out / FILENAME
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        return target
    with urllib.request.urlopen(URL, timeout=60) as response:  # a fixed https URL
        data = verified(response.read())
    out.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--iscc", type=Path, required=True, help="path of ISCC.exe")
    parser.add_argument("--out", type=Path, required=True, help="download directory")
    args = parser.parse_args(argv)
    print(messages_path(args.iscc, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
