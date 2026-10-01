from __future__ import annotations

from matplotlib.colors import to_hex
from matplotlib.figure import Figure

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.ui.plots import plot_decay, plot_frequency_response
from roomscope.ui.theme import color_scheme, plot_colors, style_figure
from tests.conftest import make_rir


def test_stylesheet_keeps_chinese_section_labels_and_shortcut_badges() -> None:
    """Letter-spacing pulls Chinese characters apart, and a 22px badge clips ⌃1."""
    from roomscope.ui.theme import stylesheet

    css = stylesheet()
    assert "letter-spacing" not in css
    badge = css.split('QLabel[role="badge"]', 1)[1].split("}", 1)[0]
    assert "max-width" not in badge
    assert "min-height: 22px" in badge
    report = css.split('QPlainTextEdit[report="true"]', 1)[1].split("}", 1)[0]
    assert "font-family" not in report


def test_decay_and_fr_plots_use_linestyle_not_only_colour(short_sweep) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(recording, Reference.from_settings(short_sweep))
    decay = Figure()
    plot_decay(decay, result)
    styles = {line.get_linestyle() for line in decay.axes[0].lines}
    assert len(styles) > 1
    fr = Figure()
    plot_frequency_response(fr, result)
    fr_styles = {line.get_linestyle() for line in fr.axes[0].lines}
    assert ":" in fr_styles
    assert "-" in fr_styles


def test_plot_chrome_follows_color_scheme(short_sweep, monkeypatch) -> None:
    monkeypatch.setenv("ROOMSCOPE_COLOR_SCHEME", "dark")
    assert color_scheme() == "dark"
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(recording, Reference.from_settings(short_sweep))
    fig = Figure()
    plot_decay(fig, result)
    assert to_hex(fig.patch.get_facecolor()[:3]) == plot_colors()["bg"]
    monkeypatch.setenv("ROOMSCOPE_COLOR_SCHEME", "light")
    style_figure(fig)
    assert to_hex(fig.patch.get_facecolor()[:3]) == plot_colors()["bg"]
