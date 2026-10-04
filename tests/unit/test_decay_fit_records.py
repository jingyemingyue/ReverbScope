"""Additive decay results retain provenance and fail clearly on malformed JSON."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator, ValidationError

from roomscope.errors import ConfigurationError, SessionError
from roomscope.models.configuration import AnalysisSettings
from roomscope.models.result import DecayComponent, MultiDecayFit, Validity
from roomscope.models.result_load import multi_decay_fit_from_dict
from roomscope.models.session import MeasurementSession
from roomscope.schemas import load_schema


def _fit() -> MultiDecayFit:
    return MultiDecayFit(
        method="block-power exponential fit",
        validity=Validity.VALID,
        components=(DecayComponent(0.3, 0.8, 0.01), DecayComponent(1.2, 0.2, 0.05)),
        noise_relative_power=1e-6,
        residual_rms_db=0.4,
        bic_difference=20.0,
        fit_start_s=0.001,
        fit_end_s=2.0,
        initializer="neural",
        initializer_model="synthetic-v1",
        initializer_parameters=2245,
        initializer_sha256="a" * 64,
    )


def _validator() -> Draft202012Validator:
    schema = load_schema("result")
    return Draft202012Validator({"$ref": "#/$defs/multi_decay", "$defs": schema["$defs"]})


def test_fit_roundtrip_preserves_diagnostics_and_provenance() -> None:
    fit = _fit()
    _validator().validate(fit.to_dict())
    assert multi_decay_fit_from_dict(fit.to_dict()) == fit
    assert multi_decay_fit_from_dict(None) is None
    marked = fit.marked_unreliable("clipped recording")
    assert marked.components == fit.components
    assert marked.validity is Validity.UNRELIABLE
    assert marked.marked_unreliable("clipped recording") == marked
    withheld = marked.not_computed("excitation unknown")
    assert withheld.validity is Validity.NOT_COMPUTED and not withheld.components
    assert withheld.noise_relative_power is None and withheld.residual_rms_db is None
    assert withheld.initializer_sha256 == fit.initializer_sha256
    assert "clipped recording" in (withheld.reason or "")
    assert multi_decay_fit_from_dict(withheld.to_dict()) == withheld


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("components", {}),
        ("components", [{"rt60_s": 0.0, "relative_power": 0.5}]),
        ("components", [{"rt60_s": 0.4, "relative_power": 2.0}]),
        ("components", [{"rt60_s": "0.4", "relative_power": 0.5}]),
        ("components", [{"rt60_s": 0.4}]),
        ("components", []),
        ("components", [{"rt60_s": t, "relative_power": 1 / 3} for t in (0.2, 0.4, 0.8)]),
        ("components", [{"rt60_s": t, "relative_power": 0.5} for t in (1.2, 0.3)]),
        ("components", [{"rt60_s": 0.4, "relative_power": 0.5}]),
        ("validity", "invented"),
        ("residual_rms_db", float("nan")),
        ("noise_relative_power", float("inf")),
        ("bic_difference", True),
        ("fit_start_s", None),
        ("fit_end_s", -1.0),
        ("initializer_parameters", "2245"),
        ("initializer_parameters", -1),
        ("initializer", "remote"),
        ("initializer_sha256", "unknown"),
        ("validity", "not_computed"),
        ("reason", {"hidden": "failure"}),
    ],
)
def test_malformed_fit_values_raise_session_error(field: str, value: object) -> None:
    payload = {**_fit().to_dict(), field: value}
    with pytest.raises(SessionError):
        multi_decay_fit_from_dict(payload)


@pytest.mark.parametrize("kind", ["unknown", "bad_component", "bad_sha", "empty_valid"])
def test_schema_checks_new_fit_objects_without_requiring_legacy_fields(kind: str) -> None:
    payload = copy.deepcopy(_fit().to_dict())
    if kind == "unknown":
        payload["claimed_iso_rt60"] = 0.3
    elif kind == "bad_component":
        payload["components"][0]["rt60_std_s"] = -1.0
    elif kind == "bad_sha":
        payload["initializer_sha256"] = "unknown"
    else:
        payload["components"] = []
    with pytest.raises(ValidationError):
        _validator().validate(payload)


def test_opt_in_settings_preserve_old_defaults_and_session_roundtrips() -> None:
    assert "decay_fit" not in AnalysisSettings().to_dict()
    assert AnalysisSettings.from_dict({}).decay_fit == "off"
    enabled = AnalysisSettings(decay_fit="neural")
    assert AnalysisSettings.from_dict(enabled.to_dict()) == enabled
    session = MeasurementSession(analysis_settings=enabled)
    assert MeasurementSession.from_dict(session.to_dict()).analysis_settings == enabled
    with pytest.raises(ConfigurationError, match="decay_fit"):
        replace(enabled, decay_fit="unsupported")
