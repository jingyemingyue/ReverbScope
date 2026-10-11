from __future__ import annotations

from matplotlib.colors import to_hex
from matplotlib.figure import Figure

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.ui.plots import plot_decay, plot_frequency_response
from reverbscope.ui.theme import color_scheme, plot_colors, style_figure
from tests.conftest import make_rir


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
    """The side view draws the tapes (dotted while they are examples) and,
    once solved, the derived lengths dashed; the 3D picture draws the
    position ring. Neither invents a room. In Chinese, the labels stay in
    Chinese.
    """
    import numpy as np
    from matplotlib.figure import Figure

    from reverbscope.i18n import activate
    from reverbscope.models.result import PlacementLength, PlacementResult, Validity
    from reverbscope.ui.plots import (
        plot_placement_3d,
        plot_placement_illustration,
        plot_placement_result,
    )
    from tests.zh_tokens import english_words

    fig = Figure()
    hint = plot_placement_illustration(fig, distance_m=None, mic_height_m=None)
    assert "not your room" in hint
    assert fig.axes and fig.axes[0].name == "rectilinear"
    # Nothing measured: every line that is not the reference plane is an example.
    styles = {line.get_linestyle() for line in fig.axes[0].lines if len(line.get_xdata()) == 2}
    assert ":" in styles and "--" not in styles
    hint = plot_placement_illustration(fig, distance_m=2.0, mic_height_m=1.1)
    assert "you entered" in hint
    assert "-" in {line.get_linestyle() for line in fig.axes[0].lines}

    measured = PlacementResult(
        tier=2,
        candidates=(),
        source_height_m=PlacementLength(1.2, Validity.VALID),
        ceiling_height_m=PlacementLength(3.1, Validity.VALID),
        horizontal_separation_m=PlacementLength(1.5, Validity.VALID),
        speed_of_sound_m_s=343.0,
        temperature_c=20.0,
        temperature_assumed=False,
        distance_m=1.8,
        mic_height_m=0.4,
    )
    fig = Figure()
    hint = plot_placement_result(fig, measured)
    assert "dashed" in hint and "does not pick one" in hint
    assert "--" in {line.get_linestyle() for line in fig.axes[0].lines}
    fig = Figure()
    hint = plot_placement_3d(fig, measured)
    assert "ring" in hint and "No wall" in hint
    rings = []
    for line in fig.axes[0].lines:
        _x, _y, z = line.get_data_3d()
        if len(_x) > 40 and abs(float(np.mean(z)) - 1.2) < 1e-6:
            rings.append(line)
    assert len(rings) == 1

    activate("zh_CN")
    try:
        fig = Figure()
        hints = [
            plot_placement_illustration(fig, distance_m=None, mic_height_m=None),
            plot_placement_illustration(fig, distance_m=2.0, mic_height_m=None),
            plot_placement_illustration(fig, distance_m=2.0, mic_height_m=1.1),
            plot_placement_result(fig, measured),
            plot_placement_result(fig, None),
            plot_placement_3d(fig, measured),
            plot_placement_3d(fig, None),
        ]
        texts = [t.get_text() for t in fig.findobj(lambda o: hasattr(o, "get_text"))]
        texts = [text for text in [*texts, *hints] if text]
        found = [word for text in texts for word in english_words(text)]
        assert found == [], found
    finally:
        activate("en")


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
    monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", "dark")
    assert color_scheme() == "dark"
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(recording, Reference.from_settings(short_sweep))
    fig = Figure()
    plot_decay(fig, result)
    assert to_hex(fig.patch.get_facecolor()[:3]) == plot_colors()["bg"]
    monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", "light")
    style_figure(fig)
    assert to_hex(fig.patch.get_facecolor()[:3]) == plot_colors()["bg"]


def test_decay_legend_gives_the_reason_a_band_has_no_rt60() -> None:
    """Every band without an RT60 was labelled "insufficient range", also the
    ones outside the sweep (the table said n/a)."""
    from reverbscope.models.configuration import SweepSettings

    sweep = SweepSettings(duration_s=2.0, post_silence_s=1.5, start_hz=300.0)
    result = analyze(
        synthetic_recording(sweep, make_rir(48000, rt60_s=0.4), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    fig = Figure()
    plot_decay(fig, result)
    labels = fig.axes[0].get_legend_handles_labels()[1]
    low = next(label for label in labels if label.startswith("63 Hz"))
    assert "outside the excitation range" in low


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


def test_every_octave_band_has_its_own_dash_pattern(short_sweep) -> None:
    """The user guide: octave bands use changing dash patterns so colour is
    not the only cue. Five styles for eight bands repeated three of them, and
    1 kHz was solid like Broadband."""
    result = analyze(
        synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.35)),
        Reference.from_settings(short_sweep),
    )
    fig = Figure()
    plot_decay(fig, result)
    lines = fig.axes[0].lines
    assert len(lines) == 1 + len(result.decay.bands) >= 9
    patterns = [tuple(line._unscaled_dash_pattern[1] or ()) for line in lines]
    assert patterns[0] == ()  # Broadband is solid
    assert all(patterns[1:]), "a band is drawn solid like Broadband"
    assert len(set(patterns[1:])) == len(patterns) - 1


def test_a_session_saved_without_curves_says_so_on_the_fr_and_decay_charts(
    short_sweep, tmp_path
) -> None:
    """A session saved with --no-curves drew an empty Frequency Response
    axis and an empty Decay axis with every band in its legend, as if the
    measurement had failed; the Noise tab already said why it was empty."""
    from reverbscope.io.session_store import load_measurement, save_measurement
    from reverbscope.models.session import MeasurementSession

    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.35), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    folder = tmp_path / "no-curves"
    save_measurement(
        folder, MeasurementSession(), result, include_curves=False, copy_recording=False
    )
    loaded = load_measurement(folder).result
    for plot, text in (
        (plot_frequency_response, "No frequency response stored with this session"),
        (plot_decay, "No decay curves stored with this session"),
    ):
        fig = Figure()
        plot(fig, loaded)
        axes = fig.axes[0]
        assert [item.get_text() for item in axes.texts] == [text]
        assert not axes.axison
        assert axes.get_legend() is None
