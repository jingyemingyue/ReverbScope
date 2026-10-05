"""Load PySide6 so matplotlib's QtAgg backend can import ``__version__``.

The ``gui`` extra installs ``PySide6_Essentials`` (LGPL) rather than the
PySide6 meta-package, which also pulls ``PySide6_Addons`` and its GPL-only
modules. Essentials is a namespace of extension modules and does not define
``PySide6.__version__``; matplotlib 3.x ``qt_compat`` imports that name.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import PySide6


def ensure_pyside6() -> None:
    """Define ``PySide6.__version__`` when only Essentials is installed."""
    if getattr(PySide6, "__version__", None):
        return
    for dist in ("PySide6_Essentials", "PySide6"):
        try:
            PySide6.__version__ = version(dist)
            return
        except PackageNotFoundError:
            continue
    PySide6.__version__ = "0"
