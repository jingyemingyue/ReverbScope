"""Experimental guided assistant: diagnosis, privacy, and no invented numbers."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from reverbscope.experimental.guided.catalog import FindingCopy, resolve_copy
from reverbscope.experimental.guided.compare import Change, compare_guidance
from reverbscope.experimental.guided.config import (
    DataLevel,
    GuidedSettings,
    export_settings,
    save_guided_settings,
)
from reverbscope.experimental.guided.context import (
    CloudContextBuilder,
    assert_no_secret,
    attachment_payload,
    sanitize_issue_report,
    sanitize_public_query,
    session_explanation_record,
    validate_block,
)
from reverbscope.experimental.guided.engine import diagnose
from reverbscope.experimental.guided.explain import CloudModelProvider, explain_findings
from reverbscope.experimental.guided.findings import (
    Confidence,
    EvidenceValue,
    FindingType,
    Priority,
    Severity,
    StructuredFinding,
    ValidityState,
)
from reverbscope.experimental.guided.knowledge import (
    LocalModelLibrary,
    LocalModelManifest,
    OnlineKnowledge,
    verify_file,
)
from reverbscope.experimental.guided.planner import Expertise, plan_recommendations
from reverbscope.experimental.guided.privacy import (
    REDACTOR,
    CredentialVault,
    HttpResponse,
    NetworkClient,
    NetworkPolicy,
    Purpose,
    StoreChoice,
    mask_key,
    reveal_key,
)
from reverbscope.experimental.guided.report import render_text
from reverbscope.experimental.guided.service import improvement_payload, run_guided
from reverbscope.experimental.guided.snapshot import MeasurementSnapshot, ReflectionView
from reverbscope.experimental.guided.thresholds import ALL_THRESHOLDS
from tests.zh_tokens import english_words


class RecordingTransport:
    def __init__(
        self, response: HttpResponse | None = None, error: Exception | None = None
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = response or HttpResponse(200, {"choices": []}, "")
        self.error = error

    def request_json(self, method, url, headers, body, timeout_s):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if self.error:
            raise self.error
        return self.response


def _finding(kind: FindingType, **evidence: float) -> StructuredFinding:
    values = tuple(EvidenceValue(key, value, "dB") for key, value in evidence.items())
    return StructuredFinding(
        finding_id=f"{kind.value}:0",
        type=kind,
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        validity=ValidityState.VALID,
        validity_reason=None,
        priority=Priority.P1,
        evidence=values,
        possible_cause_ids=("nearby_hard_surface",),
        recommendation_id="move_or_cover",
    )


def _reflection_snapshot() -> MeasurementSnapshot:
    return MeasurementSnapshot(
        reflections=(ReflectionView(4.8, -7.2),),
        recording_peak_dbfs=-12.0,
    )


def test_thresholds_are_documented() -> None:
    names = {item.name for item in ALL_THRESHOLDS}
    assert "strong_reflection_level_db" in names
    for item in ALL_THRESHOLDS:
        assert item.unit
        assert item.rationale
        assert item.limitations


def test_strong_early_reflection_uses_measured_numbers() -> None:
    found = diagnose(_reflection_snapshot())
    kinds = [item.type for item in found]
    assert FindingType.STRONG_EARLY_REFLECTION in kinds
    reflection = next(item for item in found if item.type is FindingType.STRONG_EARLY_REFLECTION)
    assert reflection.evidence_map()["delay_ms"] == 4.8
    assert reflection.evidence_map()["relative_level_db"] == -7.2
    assert reflection.validity is ValidityState.VALID


def test_invalid_t30_carries_no_number() -> None:
    found = diagnose(
        MeasurementSnapshot(
            broadband_t20_validity="insufficient_decay_range",
            broadband_t30_validity="insufficient_decay_range",
            broadband_t30_reason="insufficient_decay_range",
            broadband_rt60_s=0.72,
        )
    )
    withheld = next(item for item in found if item.type is FindingType.INSUFFICIENT_DECAY_RANGE)
    assert withheld.validity is ValidityState.INVALID
    assert withheld.priority is Priority.P0
    assert all(
        item.value is None or not isinstance(item.value, float) for item in withheld.evidence
    )
    assert withheld.evidence == ()


def test_beginner_sees_one_next_action() -> None:
    found = diagnose(
        MeasurementSnapshot(
            reflections=(ReflectionView(4.8, -7.2),),
            broadband_t20_validity="insufficient_decay_range",
            broadband_t30_validity="insufficient_decay_range",
        )
    )
    plan = plan_recommendations(found, Expertise.BEGINNER)
    assert plan.next_best is not None
    assert plan.next_best.priority is Priority.P0
    assert len(plan.visible) == 1


def test_compare_has_no_room_score_and_is_deterministic() -> None:
    before = MeasurementSnapshot(
        reflections=(ReflectionView(4.8, -7.2),),
        noise_rms_dbfs=-40.0,
    )
    after = MeasurementSnapshot(
        reflections=(ReflectionView(5.1, -14.0),),
        noise_rms_dbfs=-40.5,
    )
    base = diagnose(before)
    cand = diagnose(after)
    guidance = compare_guidance(before, after, base, cand)
    assert guidance.to_dict()["room_score"] is None
    reflection = next(item for item in guidance.items if item.topic == "early_reflection")
    assert reflection.change in {Change.IMPROVED, Change.SLIGHTLY_IMPROVED}
    again = compare_guidance(before, after, base, cand)
    assert again.overall is guidance.overall


def test_catalog_covers_every_finding_in_english_and_chinese() -> None:
    for kind in FindingType:
        for language in ("en", "zh-CN"):
            copy = resolve_copy(kind, language)
            assert copy.complete
            assert copy.copy.title
            assert "desk caused" not in copy.copy.action
            blob = " ".join(
                [
                    copy.copy.title,
                    copy.copy.what,
                    copy.copy.why,
                    copy.copy.impact,
                    *copy.copy.causes,
                    copy.copy.action,
                    copy.copy.verify,
                ]
            )
            if language == "zh-CN":
                assert english_words(blob) == []


def test_partial_languages_fall_back_without_pretending() -> None:
    copy = resolve_copy(FindingType.CLIPPING_DETECTED, "ja")
    assert copy.complete is False
    assert copy.language == "en"
    assert copy.notice


def test_template_explains_with_no_model_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    found = diagnose(_reflection_snapshot())
    bundle = explain_findings(found, GuidedSettings(), language="zh-CN")
    assert bundle.source == "template"
    assert bundle.sent is False
    text = render_text(found, plan_recommendations(found, "beginner"), bundle, language="zh-CN")
    assert "内置说明" in text
    assert english_words(text) == []
    assert "4.8" in text
    assert "-7.2" in text


def test_validator_rejects_invented_numbers_causes_and_invalid_metrics() -> None:
    finding = _finding(FindingType.STRONG_EARLY_REFLECTION, delay_ms=4.8, relative_level_db=-7.2)
    assert validate_block("这里存在较强的早期反射。", finding).accepted
    assert not validate_block("The delay is 12.5 ms.", finding).accepted
    assert not validate_block("This is the desk.", finding).accepted
    assert not validate_block("就是桌面造成的。", finding).accepted
    invalid = StructuredFinding(
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
    assert not validate_block("T30 approximately 0.72 s", invalid).accepted
    assert not validate_block("confidence is low", finding).accepted
    assert not validate_block("Please lift the safety ground.", finding).accepted


def test_cloud_failure_falls_back_and_malformed_json_is_rejected() -> None:
    transport = RecordingTransport(error=TimeoutError("timed out sk-secret-token"))
    settings = GuidedSettings(
        explanation_engine="cloud",
        cloud_explanation_enabled=True,
        cloud_consent="always",
        provider_id="openai",
        model_id="user-selected-model",
    )
    bundle = explain_findings(
        diagnose(_reflection_snapshot()),
        settings,
        language="en",
        api_key="sk-secret-token",
        transport=transport,
    )
    assert bundle.source == "template"
    assert bundle.sent is False
    assert "sk-secret" not in bundle.notice
    assert "built-in offline explanation" in render_text(
        diagnose(_reflection_snapshot()),
        plan_recommendations(diagnose(_reflection_snapshot())),
        bundle,
        language="en",
    )


def test_provider_cannot_overrule_a_comparison() -> None:
    before = MeasurementSnapshot(reflections=(ReflectionView(4.8, -7.0),))
    after = MeasurementSnapshot(reflections=(ReflectionView(4.8, -4.0),))
    guidance = compare_guidance(before, after, diagnose(before), diagnose(after))
    finding = diagnose(before)[0]
    assert guidance.overall in {Change.WORSE, Change.MIXED}
    assert not validate_block("B is better overall.", finding, comparison=guidance).accepted


def test_privacy_and_offline_block_cloud_even_with_a_key() -> None:
    transport = RecordingTransport(
        HttpResponse(200, {"choices": [{"message": {"content": '{"blocks": []}'}}]}, "")
    )
    settings = GuidedSettings(
        explanation_engine="cloud",
        cloud_explanation_enabled=True,
        cloud_consent="always",
        provider_id="openai",
        model_id="some-model",
        privacy_mode=True,
    )
    bundle = explain_findings(
        diagnose(_reflection_snapshot()),
        settings,
        language="en",
        api_key="sk-secret-token",
        transport=transport,
        privacy=True,
    )
    assert transport.calls == []
    assert bundle.sent is False
    offline = NetworkPolicy(offline=True, allow_cloud_ai=True)
    assert offline.allows(Purpose.CLOUD_AI) is False


def test_payload_is_minimal_previewable_and_has_no_audio() -> None:
    settings = GuidedSettings(data_level=DataLevel.MINIMAL.value, expertise="beginner")
    found = diagnose(_reflection_snapshot())
    payload = CloudContextBuilder().build(found, settings, language="zh-CN")
    preview = CloudContextBuilder().build(found, settings, language="zh-CN")
    assert payload.to_json() == preview.to_json()
    blob = payload.to_json()
    assert "samples" not in payload.body
    assert "waveform" not in blob
    assert "room_name" not in blob
    assert "strong_early_reflection" in blob
    assert "4.8" in blob
    with pytest.raises(PermissionError):
        attachment_payload(explicit_upload=False, kind="audio")


def test_detailed_payload_keeps_only_valid_band_numbers() -> None:
    settings = GuidedSettings(
        data_level=DataLevel.DETAILED.value, generic_device_model="Generic USB"
    )
    payload = CloudContextBuilder().build(
        (),
        settings,
        language="en",
        bands=((125.0, None, "insufficient_decay_range"), (1000.0, 0.4, "valid")),
    )
    summaries = payload.body["band_summaries"]
    assert summaries == [{"center_hz": 1000.0, "rt60_s": 0.4, "t30_validity": "valid"}]
    assert payload.body["generic_device_model"] == "Generic USB"


def test_key_never_lands_in_settings_telemetry_export_or_session() -> None:
    secret = "sk-live-example-key-should-not-leak"
    settings = GuidedSettings(
        share_anonymous_usage=True,
        share_hardware_compatibility=True,
        provider_id="openai",
        model_id="some-model",
    )
    path = save_guided_settings(settings)
    path.write_text(
        path.read_text(encoding="utf-8").replace("{", '{"api_key": "' + secret + '", ', 1),
        encoding="utf-8",
    )
    from reverbscope.experimental.guided.config import load_guided_settings

    reloaded = load_guided_settings()
    assert secret not in path.read_text(encoding="utf-8") or "api_key" not in reloaded.to_dict()
    save_guided_settings(reloaded)
    assert secret not in path.read_text(encoding="utf-8")
    report = run_guided_from_snapshot()
    payload = improvement_payload(settings, report, secret=secret)
    assert payload is not None
    assert_no_secret(payload, secret)
    exported = export_settings(settings)
    assert exported["credentials_included"] is False
    assert "api_key" not in exported
    record = session_explanation_record("cloud", "openai", "some-model")
    assert "key" not in record
    issue = sanitize_issue_report(
        {
            "provider": "openai",
            "model": "some-model",
            "headers": {"Authorization": f"Bearer {secret}"},
            "api_key": secret,
            "prompt": "full prompt",
            "status": 401,
        }
    )
    assert secret not in json.dumps(issue)
    assert "headers" not in issue
    assert issue["provider"] == "openai"
    vault = CredentialVault()
    vault.keyring.available = lambda: False  # type: ignore[method-assign]
    refused = vault.store("openai", secret, StoreChoice.SECURE)
    assert refused.stored is False
    assert secret not in path.read_text(encoding="utf-8")
    session = vault.store("openai", secret, StoreChoice.SESSION)
    assert session.stored is True
    assert secret not in path.read_text(encoding="utf-8")
    assert mask_key(secret) == "••••••••••••••••"
    assert secret not in mask_key(secret)
    with pytest.raises(PermissionError):
        reveal_key(secret, confirmed=False)


def run_guided_from_snapshot():
    from reverbscope.experimental.guided.explain import ExplanationBundle
    from reverbscope.experimental.guided.service import GuidedReport

    snapshot = _reflection_snapshot()
    findings = diagnose(snapshot)
    plan = plan_recommendations(findings, Expertise.BEGINNER)
    bundle = ExplanationBundle((), "template", "builtin", "", "")
    return GuidedReport(snapshot, findings, plan, bundle, None, "en")


def test_redactor_strips_credentials() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz"
    raw = f"Authorization: Bearer {secret} x-api-key: {secret} api_key={secret}"
    cleaned = REDACTOR.redact(raw)
    assert secret not in cleaned
    assert "Bearer " not in cleaned or secret not in cleaned


def test_test_connection_sends_no_measurement() -> None:
    transport = RecordingTransport(HttpResponse(200, {}, ""))
    client = NetworkClient(NetworkPolicy(allow_cloud_ai=True), transport)
    provider = CloudModelProvider("openai", "user-model", "sk-test-key", client)
    result = provider.test_connection()
    assert result.ok
    body = transport.calls[0]["body"]
    assert isinstance(body, dict)
    blob = json.dumps(body)
    assert "delay_ms" not in blob
    assert "strong_early_reflection" not in blob
    assert "Reply with the single word OK." in blob


def test_custom_endpoint_requires_acknowledgement() -> None:
    client = NetworkClient(NetworkPolicy(allow_cloud_ai=True), RecordingTransport())
    provider = CloudModelProvider(
        "openai_compatible",
        "local-model",
        "sk-test-key",
        client,
        base_url="https://example.internal/v1",
    )
    with pytest.raises(PermissionError):
        provider.test_connection()


def test_local_model_is_optional_and_checked() -> None:
    library = LocalModelLibrary(None)
    assert library.available() is False
    assert library.describe()["installed"] is False
    missing = Path("no-such-model.bin")
    manifest = LocalModelManifest("small", 10, "test-license", "abc", missing)
    assert LocalModelLibrary(manifest).available() is False
    assert verify_file(missing, "abc") is False


def test_online_query_strips_measurements_and_stays_off() -> None:
    cleaned = sanitize_public_query("sample rate 48000 file /Users/me/take.wav delay 4.8")
    assert "48000" not in cleaned
    assert "4.8" not in cleaned
    assert "/Users" not in cleaned
    hit = OnlineKnowledge(NetworkClient(NetworkPolicy())).lookup(FindingType.SAMPLE_RATE_MISMATCH)
    assert hit.online is False
    assert "48000" not in hit.query


def test_measurement_core_does_not_import_the_assistant() -> None:
    root = Path("src/reverbscope")
    for relative in ("core", "audio", "interpretation"):
        for path in (root / relative).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                assert all("experimental" not in name for name in names), path


def test_real_analysis_can_drive_the_guide() -> None:
    from reverbscope.audio.fake import make_rir
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.models.configuration import SweepSettings

    settings = SweepSettings(
        sample_rate=48000, duration_s=1.0, pre_silence_s=0.2, post_silence_s=0.4
    )
    room = make_rir(
        48000,
        rt60_s=0.35,
        reflections=[(0.0048, 10 ** (-7.2 / 20))],
        length_s=1.0,
        diffuse_level=0.005,
        seed=2,
    )
    recorded = synthetic_recording(settings, room, noise_rms=2e-4, gain=0.25, seed=2)
    result = analyze(recorded, Reference.from_settings(settings))
    report = run_guided(result, language="en", expertise="beginner")
    assert report.stable_feature is False
    assert report.experimental is True
    kinds = {item.type for item in report.findings}
    assert FindingType.STRONG_EARLY_REFLECTION in kinds
    assert "Built-in explanation" in report.text()
    assert (
        "room score" not in report.text().lower() or "no single room score" in report.text().lower()
    )


def test_guided_cli_reads_a_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from reverbscope.cli.main import main
    from reverbscope.experimental.guided.snapshot import snapshot_from_result

    del snapshot_from_result
    from reverbscope.audio.fake import make_rir
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.configuration import SweepSettings
    from reverbscope.models.session import MeasurementSession

    sweep = SweepSettings(sample_rate=48000, duration_s=1.0, pre_silence_s=0.2, post_silence_s=0.4)
    room = make_rir(48000, rt60_s=0.3, reflections=[(0.005, 0.45)], length_s=1.0, seed=3)
    recorded = synthetic_recording(sweep, room, noise_rms=1e-4, gain=0.2, seed=3)
    result = analyze(recorded, Reference.from_settings(sweep))
    folder = tmp_path / "take"
    save_measurement(folder, MeasurementSession(mode="universal_daw"), result)
    code = main(["--format", "json", "guided", "--result", str(folder)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["experimental"] is True
    assert payload["stable_feature"] is False
    assert payload["source"] == "template"


def test_copy_strings_have_no_digits() -> None:
    """The catalog must not be where measurement numbers are invented."""
    for kind in FindingType:
        copy: FindingCopy = resolve_copy(kind, "en").copy
        blob = copy.what + copy.why + copy.action
        assert not any(character.isdigit() for character in blob)


def test_chinese_assistant_labels_have_no_english() -> None:
    from reverbscope.experimental.guided.setup import assistant_labels

    labels = assistant_labels("zh-CN")
    assert english_words("\n".join(labels.values())) == []
    assert "OpenAI" not in labels["provider_openai"]
    assert assistant_labels("en")["provider_openai"] == "OpenAI"
    assert labels["engine_builtin"] != labels["engine_cloud"]


def test_missing_key_never_opens_the_network() -> None:
    transport = RecordingTransport()
    settings = GuidedSettings(
        explanation_engine="cloud",
        cloud_explanation_enabled=True,
        cloud_consent="always",
        provider_id="openai",
        model_id="user-model",
    )
    found = diagnose(_reflection_snapshot())
    bundle = explain_findings(found, settings, language="zh-CN", api_key="", transport=transport)
    assert transport.calls == []
    assert bundle.sent is False
    text = render_text(found, plan_recommendations(found, "beginner"), bundle, language="zh-CN")
    assert "还没有配置密钥" in text
    assert english_words(text) == []


def test_environment_key_is_not_saved_or_previewed(monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope.experimental.guided.config import settings_path
    from reverbscope.experimental.guided.setup import preview_without_measurement, resolve_api_key

    secret = "sk-env-only-not-saved-zzzz"
    monkeypatch.setenv("REVERBSCOPE_API_KEY", secret)
    vault = CredentialVault()
    assert resolve_api_key("openai", vault) == secret
    assert resolve_api_key("", vault) == ""
    settings = GuidedSettings(
        provider_id="openai",
        model_id="user-model",
        explanation_engine="cloud",
        cloud_explanation_enabled=True,
        cloud_consent="always",
    )
    assert secret not in preview_without_measurement(settings, "en")
    save_guided_settings(settings)
    assert secret not in settings_path().read_text(encoding="utf-8")


def test_cli_cloud_sends_the_vault_key_and_not_the_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.audio.fake import make_rir
    from reverbscope.cli.main import main
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.experimental.guided.privacy import HttpResponse, NetworkClient
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.configuration import SweepSettings
    from reverbscope.models.session import MeasurementSession

    secret = "sk-cli-vault-secret-value"
    vault = CredentialVault()
    vault.keyring.available = lambda: False  # type: ignore[method-assign]
    assert vault.store("openai", secret, StoreChoice.SESSION).stored
    monkeypatch.setattr("reverbscope.experimental.guided.privacy.process_vault", lambda: vault)
    calls: list[dict[str, object]] = []

    def fake_request(
        self: NetworkClient,
        purpose: object,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, object] | None,
        timeout_s: float,
    ) -> HttpResponse:
        del self, purpose, method, timeout_s
        calls.append({"url": url, "headers": dict(headers), "body": body})
        user = ""
        messages = body.get("messages") if isinstance(body, dict) else None
        if isinstance(messages, list) and len(messages) > 1 and isinstance(messages[1], dict):
            user = str(messages[1].get("content", ""))
        payload = json.loads(user)
        blocks = [
            {
                "finding_id": item["finding_id"],
                "explanation": "A strong early reflection is present.",
            }
            for item in payload["findings"]
        ]
        content = json.dumps({"blocks": blocks})
        return HttpResponse(200, {"choices": [{"message": {"content": content}}]}, "")

    monkeypatch.setattr(NetworkClient, "request_json", fake_request)
    sweep = SweepSettings(sample_rate=48000, duration_s=1.0, pre_silence_s=0.2, post_silence_s=0.4)
    room = make_rir(48000, rt60_s=0.3, reflections=[(0.005, 0.45)], length_s=1.0, seed=4)
    recorded = synthetic_recording(sweep, room, noise_rms=1e-4, gain=0.2, seed=4)
    result = analyze(recorded, Reference.from_settings(sweep))
    folder = tmp_path / "take"
    save_measurement(folder, MeasurementSession(mode="universal_daw"), result)
    code = main(
        [
            "--format",
            "json",
            "guided",
            "--result",
            str(folder),
            "--engine",
            "cloud",
            "--provider",
            "openai",
            "--model",
            "user-model",
            "--enable-cloud",
            "--send-once",
            "--expertise",
            "beginner",
        ]
    )
    assert code == 0
    captured = capsys.readouterr().out
    assert secret not in captured
    payload = json.loads(captured)
    assert payload["source"] == "cloud"
    assert payload["explanation"]["sent"] is True
    assert calls
    headers = calls[0]["headers"]
    assert isinstance(headers, dict)
    assert secret in headers["Authorization"]
    from reverbscope.experimental.guided.config import settings_path

    assert secret not in settings_path().read_text(encoding="utf-8")
    calls.clear()
    private = main(
        [
            "--privacy-mode",
            "--format",
            "json",
            "guided",
            "--result",
            str(folder),
            "--engine",
            "cloud",
            "--provider",
            "openai",
            "--model",
            "user-model",
            "--enable-cloud",
            "--send-once",
        ]
    )
    assert private == 0
    assert calls == []
    assert secret not in capsys.readouterr().out
