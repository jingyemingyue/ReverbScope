"""Health in text reports; existing JSON output stays exactly compatible."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, cell_width
from reverbscope.cli.main import main
from reverbscope.cli.render import at_a_glance, render_analysis
from reverbscope.i18n import activate
from reverbscope.interpretation import Finding, interpret
from reverbscope.interpretation.interpreter import Severity
from reverbscope.models.result import ClippingCheck
from tests.health_fixtures import healthy_result


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("width", [24, 40, 80])
@pytest.mark.parametrize("unicode", [False, True])
def test_health_report_fits_plain_narrow_terminals(lang: str, width: int, unicode: bool) -> None:
    activate(lang)
    result = replace(healthy_result(), clipping=ClippingCheck(0.0, 3, 10, True))
    text = render_analysis(Console(color=False, unicode=unicode, width=width), result)
    heading = "Measurement Health" if lang == "en" else "测量健康"
    assert heading in text
    assert "\x1b" not in text
    assert all(cell_width(line) <= width for line in text.splitlines())
    assert ("preamp" if lang == "en" else "话放") in text
    assert ("Next step" if lang == "en" else "下一步") in text


def test_health_does_not_erase_an_existing_profile_measurement_warning() -> None:
    finding = Finding("measurement", Severity.WARNING, "An existing profile measurement warning.")
    console = Console(color=False, unicode=False, width=120)
    rows = at_a_glance(console, healthy_result(), [finding])
    quality = next(line for line in rows if "Data quality" in line)
    assert "[WARN]" in quality


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_analyze_pipe_and_json_keep_original_payload(
    lang: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.core import pipeline
    from reverbscope.io.wav import write_wav

    result = healthy_result()
    recording = write_wav(tmp_path / "recording.wav", result.impulse_response.samples, 48000)
    monkeypatch.setattr(pipeline, "analyze", lambda *_args, **_kwargs: result)
    args = [
        "--lang",
        lang,
        "analyze",
        "--recording",
        str(recording),
        "--sweep",
        str(recording),
        "--no-curves",
    ]
    assert main(["--format", "json", *args]) == 0
    payload = json.loads(capsys.readouterr().out)
    expected = result.to_dict(include_curves=False)
    expected["findings"] = [f.to_dict() for f in interpret(result)]
    assert payload == expected
    assert "health" not in payload and "measurement_health" not in payload
    assert main(["--color", "never", *args]) == 0
    text = capsys.readouterr().out
    assert ("Measurement Health" if lang == "en" else "测量健康") in text
    assert "\x1b" not in text
