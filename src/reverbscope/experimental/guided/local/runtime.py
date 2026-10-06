"""Load the trained on-device model. Nothing here contacts the network.

The file is copied only when the user installs it. A checksum or catalog
mismatch makes the model unavailable, and the assistant stays on the template.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from reverbscope.experimental.guided.explain import ExplanationBlock
from reverbscope.experimental.guided.findings import StructuredFinding
from reverbscope.experimental.guided.knowledge import (
    LocalModelLibrary,
    LocalModelManifest,
    sha256_file,
)
from reverbscope.experimental.guided.local.corpus import (
    MODEL_ID,
    Vocab,
    allowed_mask,
    build_vocab,
    canonical_text,
    finding_features,
)
from reverbscope.experimental.guided.local.train import TrainedWeights, TrainMetrics

BUNDLED_NAME = "guided-clause-v1.json"
SCHEMA = "reverbscope.guided.local_model.v1"
#: SHA-256 of the trained file shipped next to this module. A modified file is refused.
BUNDLED_SHA256 = "d4c3a99103b8aa065d1611eeeda2b969f615a890092a00d973be644b522f9c7c"


def bundled_path() -> Path:
    return Path(__file__).with_name(BUNDLED_NAME)


def _read_array(spec: dict[str, Any]) -> np.ndarray:
    shape = tuple(int(item) for item in spec["shape"])
    raw = bytes.fromhex(str(spec["hex"]))
    return np.frombuffer(raw, dtype=np.float32).reshape(shape).astype(np.float64)


def load_weights(path: Path, vocab: Vocab | None = None) -> TrainedWeights | None:
    """Return weights only when the file matches this catalog. Otherwise refuse."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    current = vocab if vocab is not None else build_vocab()
    if payload.get("catalog_fingerprint") != current.fingerprint:
        return None
    arrays = payload.get("arrays")
    if not isinstance(arrays, dict):
        return None
    try:
        metrics = payload.get("metrics")
        recorded = metrics if isinstance(metrics, dict) else {}
        safety_b = _read_array(arrays["safety_b"]).reshape(-1)
        return TrainedWeights(
            vocab=current,
            metrics=TrainMetrics(
                float(recorded.get("loss_start", 0.0)),
                float(recorded.get("loss_end", 0.0)),
                float(recorded.get("token_accuracy", 0.0)),
                float(recorded.get("safety_heldout_accuracy", 0.0)),
            ),
            W1=_read_array(arrays["W1"]),
            b1=_read_array(arrays["b1"]),
            step=_read_array(arrays["step"]),
            W_h=_read_array(arrays["W_h"]),
            W_s=_read_array(arrays["W_s"]),
            b=_read_array(arrays["b"]),
            safety_w=_read_array(arrays["safety_w"]),
            safety_b=float(safety_b[0]),
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass
class SpecializedLocalModel:
    """ExplanationProvider. Clauses come from the catalog; weights only rank them."""

    weights: TrainedWeights
    manifest: LocalModelManifest
    length: str = "balanced"
    expertise: str = "beginner"
    source: str = "local"
    library: LocalModelLibrary = field(init=False)

    def __post_init__(self) -> None:
        self.library = LocalModelLibrary(self.manifest)

    def explain(
        self,
        findings: tuple[StructuredFinding, ...],
        *,
        language: str,
        comparison: object = None,
    ) -> tuple[ExplanationBlock, ...]:
        from reverbscope.experimental.guided.catalog import normalize_language

        del comparison  # the comparison verdict is not this model's decision
        blocks: list[ExplanationBlock] = []
        for finding in findings:
            text = self._render(finding, normalize_language(language))
            if any(character.isdigit() for character in text):
                raise RuntimeError("local model emitted a digit")
            if self.weights.safety_score(text) < 0.5:
                raise RuntimeError("local model safety check failed")
            blocks.append(ExplanationBlock(finding.finding_id, text, self.source))
        return tuple(blocks)

    def _render(self, finding: StructuredFinding, language: str) -> str:
        lang = language if language in {"en", "zh-CN"} else "en"
        features = finding_features(finding, lang, self.length, self.expertise)
        mask = allowed_mask(self.weights.vocab, finding.type.value, lang)
        chosen = self.weights.generate_ids(features, mask)
        parts: list[str] = []
        for item in chosen:
            if item == self.weights.vocab.stop_id:
                break
            clause = self.weights.vocab.clauses[item]
            if clause.kind != finding.type.value or clause.language != lang:
                raise RuntimeError("local model left the finding catalog")
            parts.append(clause.text)
        if not parts:
            return canonical_text(self.weights.vocab, finding.type.value, lang, self.length)
        if lang == "zh-CN":
            return "".join(parts)
        return " ".join(parts)


def install_bundled_model(dest_dir: Path) -> LocalModelManifest:
    """Copy the trained file onto this machine. Does not download anything."""
    source = bundled_path()
    if not source.is_file():
        raise FileNotFoundError("the trained local model is not in this installation")
    if sha256_file(source) != BUNDLED_SHA256:
        raise FileNotFoundError("the trained local model failed its checksum")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / BUNDLED_NAME
    target.write_bytes(source.read_bytes())
    return LocalModelManifest(
        model_id=MODEL_ID,
        size_bytes=target.stat().st_size,
        license_name="Apache-2.0",
        sha256=BUNDLED_SHA256,
        path=target,
    )


def open_installed_model(
    path: Path,
    *,
    length: str = "balanced",
    expertise: str = "beginner",
) -> SpecializedLocalModel | None:
    if not path.is_file() or sha256_file(path) != BUNDLED_SHA256:
        return None
    weights = load_weights(path)
    if weights is None:
        return None
    manifest = LocalModelManifest(
        model_id=MODEL_ID,
        size_bytes=path.stat().st_size,
        license_name="Apache-2.0",
        sha256=BUNDLED_SHA256,
        path=path,
    )
    library = LocalModelLibrary(manifest)
    if not library.available():
        return None
    return SpecializedLocalModel(weights, manifest, length=length, expertise=expertise)


def safety_rejects(text: str, weights: TrainedWeights) -> bool:
    """True when the probe thinks the sentence is not an approved explanation."""
    return weights.safety_score(text) < 0.5
