"""The stylesheet and the one matplotlib picture left (the tape-measure schematic).

The charts of a result are pyqtgraph views; their checks are in
tests/ui/test_views.py.
"""

from __future__ import annotations


def test_stylesheet_keeps_chinese_section_labels_and_shortcut_badges() -> None:
    """Letter-spacing pulls Chinese characters apart, and a 22px badge clips ⌃1."""
    from reverbscope.ui.theme import stylesheet

    css = stylesheet()
    assert "letter-spacing" not in css
    badge = css.split('QLabel[role="badge"]', 1)[1].split("}", 1)[0]
    assert "max-width" not in badge
    assert "min-height: 22px" in badge
    report = css.split('QPlainTextEdit[report="true"]', 1)[1].split("}", 1)[0]
    assert "font-family" not in report


def test_placement_picture_is_a_schematic_not_a_room() -> None:
    """The 3D picture shows where the tapes go; it must not invent a room.

    In Chinese, the labels stay in Chinese.
    """
    from matplotlib.figure import Figure

    from reverbscope.i18n import activate
    from reverbscope.ui.plots import plot_placement_illustration
    from tests.zh_tokens import english_words

    fig = Figure()
    hint = plot_placement_illustration(fig, distance_m=None, mic_height_m=None)
    assert "not your room" in hint
    assert fig.axes and fig.axes[0].name == "3d"

    activate("zh_CN")
    try:
        fig = Figure()
        hints = [
            plot_placement_illustration(fig, distance_m=None, mic_height_m=None),
            plot_placement_illustration(fig, distance_m=2.0, mic_height_m=None),
            plot_placement_illustration(fig, distance_m=2.0, mic_height_m=1.1),
        ]
        texts = [t.get_text() for t in fig.findobj(lambda o: hasattr(o, "get_text"))]
        texts = [text for text in [*texts, *hints] if text]
        found = [word for text in texts for word in english_words(text)]
        assert found == [], found
    finally:
        activate("en")


def test_placement_surfaces_have_names_not_ids() -> None:
    from reverbscope.i18n import activate
    from reverbscope.labels import surface_text

    assert surface_text("lower_plane") == "Reference plane"
    assert surface_text("upper_plane") == "Plane above the devices"
    assert surface_text(None) == ""
    activate("zh_CN")
    try:
        assert surface_text("lower_plane") == "参考平面"
    finally:
        activate("en")
