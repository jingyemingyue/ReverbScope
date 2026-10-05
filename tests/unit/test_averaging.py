from __future__ import annotations

import pytest

from reverbscope.core.averaging import (
    ISO_3382_2_TABLE1,
    ISO_3382_2_TABLE1_SOURCE,
    average_decay,
    iso_3382_2_class,
)
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import ConfigurationError
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import Validity
from tests.conftest import make_rir


def test_table_1_values_are_the_standard_s() -> None:
    """ISO 3382-2:2008 4.3.1 Table 1 (#15): combinations 2 / 6 / 12, source
    positions 1 / 2 / 2, microphone positions 2 / 2 / 3."""
    assert ISO_3382_2_TABLE1 == {
        "survey": {"n_source": 1, "n_microphone": 2, "n_combinations": 2},
        "engineering": {"n_source": 2, "n_microphone": 2, "n_combinations": 6},
        "precision": {"n_source": 2, "n_microphone": 3, "n_combinations": 12},
    }
    assert "ISO 3382-2:2008, 4.3.1, Table 1" in ISO_3382_2_TABLE1_SOURCE


@pytest.mark.parametrize(
    ("sources", "mics", "combinations", "expected"),
    [
        (1, 1, None, "below_survey"),
        (1, 2, None, "survey"),
        (1, 12, None, "survey"),  # one source never reaches engineering
        (6, 1, None, "below_survey"),  # every class needs >= 2 microphone positions
        (2, 2, None, "survey"),  # 4 combinations < 6
        (2, 3, None, "engineering"),
        (3, 2, None, "engineering"),  # 2 microphone positions suffice for engineering
        (6, 2, None, "engineering"),  # precision needs >= 3 microphone positions
        (3, 4, None, "precision"),  # v0.4.0 wanted 6 microphone positions here
        (4, 3, None, "precision"),
        (2, 6, None, "precision"),
        (2, 3, 4, "survey"),  # only 4 of the 6 combinations measured
        (3, 4, 11, "engineering"),
        (2, 2, 99, "survey"),  # combinations cannot exceed sources x microphones
    ],
)
def test_iso_class_checks_every_row(
    sources: int, mics: int, combinations: int | None, expected: str
) -> None:
    assert iso_3382_2_class(sources, mics, combinations) == expected


def test_average_counts_repeats_as_sessions_not_positions(short_sweep: SweepSettings) -> None:
    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.4, diffuse_level=0.02),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    # Four takes at one microphone position with one source: one combination.
    repeats = average_decay([result] * 4, n_microphone_positions=1)
    assert repeats.n_combinations == 1
    assert repeats.iso_3382_2_class == "below_survey"
    # Default: every result is its own microphone position.
    spread = average_decay([result] * 3, n_source_positions=2)
    assert (spread.n_microphone_positions, spread.n_combinations) == (3, 3)
    assert spread.iso_3382_2_class == "survey"
    payload = spread.to_dict()
    assert payload["n_source_microphone_combinations"] == 3
    assert "ISO 3382-2 class survey" in " ".join(payload["notes"])
    with pytest.raises(ConfigurationError, match="combinations"):
        average_decay([result], n_source_positions=1, n_microphone_positions=2, n_combinations=3)
    # Two results cannot stand for more than two combinations.
    with pytest.raises(ConfigurationError, match="number of results"):
        average_decay(
            [result] * 2, n_source_positions=2, n_microphone_positions=3, n_combinations=6
        )


def test_average_decay_means_valid_t_only(short_sweep: SweepSettings) -> None:
    a = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.4, diffuse_level=0.02),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    b = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.6, diffuse_level=0.02),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    averaged = average_decay([a, b], session_labels=["a", "b"])
    assert averaged.n_sessions == 2
    assert averaged.iso_3382_2_class == "survey"
    broadband = next(
        band for band in averaged.bands if band.band_label == a.decay.broadband.band_label
    )
    assert broadband.t20.validity is Validity.VALID
    assert broadband.t20.count == 2
    assert broadband.t20.seconds is not None
    left = a.decay.broadband.t20.seconds
    right = b.decay.broadband.t20.seconds
    assert left is not None and right is not None
    assert broadband.t20.seconds == (left + right) / 2
    assert broadband.t20.spread_s == abs(left - right)
    payload = averaged.to_dict()
    assert "edc_db" not in str(payload)
    assert payload["confirmation_status"].startswith("ISO 3382-2:2008, 4.3.1, Table 1")


def test_project_average_counts_distinct_positions(
    tmp_path, short_sweep: SweepSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    """#15: ``reverbscope project average`` used the session count as the
    microphone-position count, so repeated takes at one position were
    labelled as a survey-class spatial average."""
    import json

    from reverbscope.cli.main import main
    from reverbscope.io.project_store import add_session, save_project
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.project import Project
    from reverbscope.models.session import MeasurementSession

    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.4, diffuse_level=0.02),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    project = tmp_path / "room"
    save_project(project, Project(name="room"))
    for name, position in (("take1", "desk"), ("take2", "desk")):
        folder = project / name
        save_measurement(
            folder, MeasurementSession(sweep_settings=short_sweep), result, copy_recording=False
        )
        add_session(project, folder, position=position)

    assert main(["project", "average", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_sessions"] == 2
    assert payload["n_microphone_positions"] == 1
    assert payload["n_source_microphone_combinations"] == 1
    assert payload["iso_3382_2_class"] == "below_survey"

    folder = project / "take3"
    save_measurement(
        folder, MeasurementSession(sweep_settings=short_sweep), result, copy_recording=False
    )
    add_session(project, folder, position="sofa")
    assert main(["project", "average", str(project)]) == 0
    text = capsys.readouterr().out
    assert "ISO 3382-2 class: survey (1 source × 2 mic, 2 combinations)" in text
    assert main(["project", "average", str(project), "--sources", "0"]) == 1
    assert "--sources must be at least 1" in capsys.readouterr().err
