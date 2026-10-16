"""Display data: what the desktop workstation draws, computed from stored results.

Nothing here imports Qt, and nothing here changes a result. Every function
takes arrays and returns new ones; the analysis numbers (EDT, T20, T30,
C50, C80, D50, noise, reflections) are never recomputed or altered.
See docs/design/GUI_2_ARCHITECTURE.md §5.
"""

from __future__ import annotations

from typing import Any

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _


class DisplayDataError(ReverbScopeError):
    """The stored data cannot be drawn this way (empty, too short, not finite).

    ``template`` is an ``N_``-marked English sentence and ``params`` fills
    its placeholders; :meth:`text` gives the sentence in the interface
    language, so a view shows the reason translated.
    """

    def __init__(self, template: str, **params: Any) -> None:
        self.template = template
        self.params = params
        super().__init__(template.format(**params) if params else template)

    def text(self) -> str:
        translated = _(self.template)
        return translated.format(**self.params) if self.params else translated
