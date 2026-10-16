"""Body text, hints and status chips stay readable on both colour schemes.

WCAG 2 AA asks for 4.5:1 on text smaller than 18 pt. Chart grids are not text
and are not held to that.
"""

from __future__ import annotations

from reverbscope.ui.theme import DARK_TOKENS, LIGHT_TOKENS, contrast_ratio


def test_text_and_status_colours_clear_wcag_aa() -> None:
    for name, palette in (("light", LIGHT_TOKENS), ("dark", DARK_TOKENS)):
        for surface in ("bg", "surface", "surface_alt"):
            assert contrast_ratio(palette["text"], palette[surface]) >= 7.0, (name, surface)
            assert contrast_ratio(palette["muted"], palette[surface]) >= 4.5, (name, surface)
        for tone in ("good", "warn", "bad", "info"):
            ratio = contrast_ratio(palette[tone], palette[f"{tone}_soft"])
            assert ratio >= 4.5, (name, tone, ratio)
        assert contrast_ratio(palette["accent_text"], palette["accent"]) >= 4.5, name
