"""The specialized local model is trained offline and cannot invent measurements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reverbscope.experimental.guided.config import GuidedSettings
from reverbscope.experimental.guided.context import validate_block
from reverbscope.experimental.guided.engine import diagnose
from reverbscope.experimental.guided.explain import explain_findings
from reverbscope.experimental.guided.findings import (
    Confidence,
    FindingType,
    Priority,
    Severity,
    StructuredFinding,
    ValidityState,
)
from reverbscope.experimental.guided.local.corpus import (
    POISON_SUFFIXES,
    build_vocab,
    canonical_text,
)
from reverbscope.experimental.guided.local.runtime import (
    install_bundled_model,
    open_installed_model,
    safety_rejects,
)
from reverbscope.experimental.guided.local.train import fit
from reverbscope.experimental.guided.snapshot import MeasurementSnapshot, ReflectionView
from tests.zh_tokens import english_words


def _reflection() -> StructuredFinding:
    found = diagnose(MeasurementSnapshot(reflections=(ReflectionView(4.8, -7.2),)))
    return next(item for item in found if item.type is FindingType.STRONG_EARLY_REFLECTION)


def test_optimizer_reduces_loss_without_using_measurements() -> None:
    weights = fit(epochs=20, copies=1)
    assert weights.metrics.loss_end < weights.metrics.loss_start * 0.5
    assert weights.metrics.token_accuracy >= 0.99
    assert weights.vocab.fingerprint == build_vocab().fingerprint


def test_shipped_model_is_catalog_locked_and_rejects_digits(tmp_path: Path) -> None:
    manifest = install_bundled_model(tmp_path)
    assert manifest.path is not None
    payload = json.loads(manifest.path.read_text(encoding="utf-8"))
    assert payload["network_used"] is False
    assert payload["trained_on"] == "catalog-only"
    assert payload["metrics"]["token_accuracy"] == 1.0
    assert payload["metrics"]["loss_end"] < payload["metrics"]["loss_start"] * 0.25
    assert payload["metrics"]["safety_heldout_accuracy"] == 1.0
    model = open_installed_model(manifest.path, length="balanced", expertise="intermediate")
    assert model is not None
    finding = _reflection()
    text = str(model.explain((finding,), language="zh-CN")[0].explanation)
    assert text == canonical_text(model.weights.vocab, finding.type.value, "zh-CN", "balanced")
    assert not any(character.isdigit() for character in text)
    assert english_words(text) == []
    assert validate_block(text, finding).accepted
    assert safety_rejects(text + POISON_SUFFIXES[0], model.weights)
    assert not safety_rejects(text, model.weights)
    raw = bytearray(manifest.path.read_bytes())
    raw[-8] = (raw[-8] + 1) % 256
    manifest.path.write_bytes(bytes(raw))
    assert open_installed_model(manifest.path) is None


def test_invalid_decay_explanation_has_no_number(tmp_path: Path) -> None:
    manifest = install_bundled_model(tmp_path)
    assert manifest.path is not None
    model = open_installed_model(manifest.path, length="detailed", expertise="expert")
    assert model is not None
    finding = StructuredFinding(
        finding_id="insufficient_decay_range:0",
        type=FindingType.INSUFFICIENT_DECAY_RANGE,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        validity=ValidityState.INVALID,
        validity_reason="insufficient_decay_range",
        priority=Priority.P0,
        evidence=(),
        possible_cause_ids=(),
        recommendation_id="more_decay_range",
    )
    text = str(model.explain((finding,), language="en")[0].explanation)
    assert not any(character.isdigit() for character in text)
    assert validate_block(text, finding).accepted
    assert "desk caused" not in text.lower()


def test_installed_model_runs_offline_and_is_off_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    finding = _reflection()
    builtin = explain_findings((finding,), GuidedSettings(), language="en")
    assert builtin.source == "template"
    assert builtin.sent is False
    manifest = install_bundled_model(tmp_path)
    settings = GuidedSettings(
        explanation_engine="local",
        local_model_path="" if manifest.path is None else str(manifest.path),
        privacy_mode=True,
        length="concise",
        expertise="beginner",
    )
    from reverbscope.experimental.guided.service import _resolve_local

    library, complete = _resolve_local(settings, None, None)
    assert library is not None and complete is not None
    guided = explain_findings(
        (finding,),
        settings,
        language="zh-CN",
        privacy=True,
        library=library,
        local_complete=complete,
    )
    assert guided.source == "local"
    assert guided.sent is False
    assert guided.model == "guided-clause-v1"
    text = guided.blocks[0].explanation
    assert "4.8" not in text
    assert "-7.2" not in text
    assert "better overall" not in text.lower()
    assert not any(character.isdigit() for character in text)
