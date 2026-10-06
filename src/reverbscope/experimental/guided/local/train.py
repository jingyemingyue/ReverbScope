"""Offline training for the specialized local explanation model.

No base model is downloaded. Parameters start at random and are fit to the
catalog with gradient descent. User measurements are not in the loss.
Run as ``python -m reverbscope.experimental.guided.local.train``.
Metrics are stored in the model file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from reverbscope.experimental.guided.findings import FindingType
from reverbscope.experimental.guided.local.corpus import (
    LENGTHS,
    MAX_LEN,
    MODEL_ID,
    POISON_SUFFIXES,
    SAFETY_DIM,
    VALIDITY,
    Vocab,
    allowed_mask,
    build_vocab,
    canonical_text,
    feature_dim,
    featurize,
    safety_features,
    target_ids,
)

HIDDEN = 64
STEP_DIM = 16
CONFIDENCE_CHOICES = ("low", "medium", "high")
PRIORITY_CHOICES = ("P0", "P1", "P2", "P3")
# Digit phrases withheld from the update, used only to score the probe.
UNSEEN_DIGIT_SUFFIXES = (" about 9.9 dB", " 8 ms later", " RT60 1.2 s")


@dataclass
class TrainMetrics:
    loss_start: float
    loss_end: float
    token_accuracy: float
    safety_heldout_accuracy: float

    def to_dict(self) -> dict[str, float]:
        return {
            "loss_start": self.loss_start,
            "loss_end": self.loss_end,
            "token_accuracy": self.token_accuracy,
            "safety_heldout_accuracy": self.safety_heldout_accuracy,
        }


@dataclass
class TrainedWeights:
    vocab: Vocab
    metrics: TrainMetrics
    W1: np.ndarray
    b1: np.ndarray
    step: np.ndarray
    W_h: np.ndarray
    W_s: np.ndarray
    b: np.ndarray
    safety_w: np.ndarray
    safety_b: float

    def generate_ids(self, features: np.ndarray, mask: np.ndarray) -> tuple[int, ...]:
        hidden = np.tanh(self.W1 @ features + self.b1)
        chosen: list[int] = []
        for position in range(MAX_LEN):
            logits = self.W_h @ hidden + self.W_s @ self.step[position] + self.b
            logits = np.where(mask, logits, -1e9)
            pick = int(np.argmax(logits))
            chosen.append(pick)
            if pick == self.vocab.stop_id:
                break
        return tuple(chosen)

    def safety_score(self, text: str) -> float:
        vec = safety_features(text)
        raw = float(self.safety_w @ vec + self.safety_b)
        raw = float(np.clip(raw, -20.0, 20.0))
        return 1.0 / (1.0 + float(np.exp(-raw)))


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    total = float(np.sum(exp))
    out: np.ndarray = exp / total
    return out


def _examples(
    vocab: Vocab, copies: int, seed: int
) -> list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]]:
    rng = np.random.default_rng(seed)
    rows: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]] = []
    for kind in FindingType:
        for language in ("en", "zh-CN"):
            mask = allowed_mask(vocab, kind.value, language)
            for length in LENGTHS:
                target = target_ids(vocab, kind.value, language, length)
                for _ in range(copies):
                    features = featurize(
                        kind.value,
                        language,
                        str(rng.choice(["beginner", "intermediate", "expert"])),
                        length,
                        str(rng.choice(list(VALIDITY))),
                        str(rng.choice(list(CONFIDENCE_CHOICES))),
                        str(rng.choice(list(PRIORITY_CHOICES))),
                    )
                    rows.append((features, mask, target))
    return rows


def _token_accuracy(
    weights: TrainedWeights, rows: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]]
) -> float:
    correct = 0
    total = 0
    for features, mask, target in rows:
        predicted = weights.generate_ids(features, mask)
        for position, expected in enumerate(target):
            total += 1
            got = predicted[position] if position < len(predicted) else weights.vocab.stop_id
            correct += int(got == expected)
    return correct / total if total else 0.0


def _mean_loss(
    weights: TrainedWeights, rows: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]]
) -> float:
    total = 0.0
    count = 0
    for features, mask, target in rows:
        hidden = np.tanh(weights.W1 @ features + weights.b1)
        for position, expected in enumerate(target):
            logits = weights.W_h @ hidden + weights.W_s @ weights.step[position] + weights.b
            logits = np.where(mask, logits, -1e9)
            total += float(-np.log(max(_softmax(logits)[expected], 1e-12)))
            count += 1
    return total / count if count else 0.0


def train_sequencer(
    vocab: Vocab,
    *,
    epochs: int = 80,
    seed: int = 20261006,
    copies: int = 2,
    lr: float = 0.05,
) -> tuple[TrainedWeights, float]:
    """Full-batch Adam. Returns weights and the loss before the first update."""
    rng = np.random.default_rng(seed)
    dim = feature_dim()
    size = vocab.size
    scale = 0.05
    weights = TrainedWeights(
        vocab=vocab,
        metrics=TrainMetrics(0.0, 0.0, 0.0, 0.0),
        W1=rng.normal(0.0, scale, (HIDDEN, dim)),
        b1=np.zeros(HIDDEN),
        step=rng.normal(0.0, scale, (MAX_LEN, STEP_DIM)),
        W_h=rng.normal(0.0, scale, (size, HIDDEN)),
        W_s=rng.normal(0.0, scale, (size, STEP_DIM)),
        b=np.zeros(size),
        safety_w=np.zeros(SAFETY_DIM),
        safety_b=0.0,
    )
    rows = _examples(vocab, copies, seed)
    start = _mean_loss(weights, rows)
    moment = {
        name: np.zeros_like(getattr(weights, name))
        for name in ("W1", "b1", "step", "W_h", "W_s", "b")
    }
    velocity = {name: np.zeros_like(value) for name, value in moment.items()}
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    for step_n in range(1, epochs + 1):
        grad = {name: np.zeros_like(value) for name, value in moment.items()}
        for features, mask, target in rows:
            hidden_pre = weights.W1 @ features + weights.b1
            hidden = np.tanh(hidden_pre)
            hidden_grad = np.zeros_like(hidden)
            for position, expected in enumerate(target):
                logits = weights.W_h @ hidden + weights.W_s @ weights.step[position] + weights.b
                logits = np.where(mask, logits, -1e9)
                delta = _softmax(logits)
                delta[expected] -= 1.0
                delta = np.where(mask, delta, 0.0)
                grad["W_h"] += np.outer(delta, hidden)
                grad["W_s"] += np.outer(delta, weights.step[position])
                grad["b"] += delta
                grad["step"][position] += weights.W_s.T @ delta
                hidden_grad += weights.W_h.T @ delta
            hidden_grad *= 1.0 - hidden**2
            grad["W1"] += np.outer(hidden_grad, features)
            grad["b1"] += hidden_grad
        scale_rows = float(len(rows) * MAX_LEN)
        for name in grad:
            grad[name] /= scale_rows
            np.clip(grad[name], -1.0, 1.0, out=grad[name])
            moment[name] = beta1 * moment[name] + (1.0 - beta1) * grad[name]
            velocity[name] = beta2 * velocity[name] + (1.0 - beta2) * (grad[name] ** 2)
            mhat = moment[name] / (1.0 - beta1**step_n)
            vhat = velocity[name] / (1.0 - beta2**step_n)
            current = getattr(weights, name)
            current -= lr * mhat / (np.sqrt(vhat) + eps)
    return weights, start


def _safe_texts(vocab: Vocab) -> list[str]:
    texts = [clause.text for clause in vocab.clauses]
    for kind in FindingType:
        for language in ("en", "zh-CN"):
            for length in LENGTHS:
                texts.append(canonical_text(vocab, kind.value, language, length))
    return texts


def _safety_rows(
    vocab: Vocab,
) -> tuple[list[tuple[np.ndarray, float]], list[tuple[np.ndarray, float]]]:
    train: list[tuple[np.ndarray, float]] = []
    held: list[tuple[np.ndarray, float]] = []
    for text in _safe_texts(vocab):
        for _ in range(len(POISON_SUFFIXES)):
            train.append((safety_features(text), 1.0))
        for suffix in POISON_SUFFIXES:
            train.append((safety_features(text + suffix), 0.0))
        for suffix in UNSEEN_DIGIT_SUFFIXES:
            held.append((safety_features(text + suffix), 0.0))
    return train, held


def train_safety(weights: TrainedWeights, *, epochs: int = 40, lr: float = 0.2) -> float:
    """Linear probe. Digit phrases in ``UNSEEN_DIGIT_SUFFIXES`` are not in the update."""
    train, held = _safety_rows(weights.vocab)
    rng = np.random.default_rng(20261006)
    weights.safety_w = rng.normal(0.0, 0.01, SAFETY_DIM)
    weights.safety_b = 0.0
    for _epoch in range(epochs):
        order = rng.permutation(len(train))
        for index in order:
            vec, label = train[int(index)]
            score = float(weights.safety_w @ vec + weights.safety_b)
            pred = 1.0 / (1.0 + float(np.exp(-np.clip(score, -20, 20))))
            error = pred - label
            weights.safety_w -= lr * error * vec
            weights.safety_b -= lr * error
    correct = 0
    for vec, label in held:
        score = float(weights.safety_w @ vec + weights.safety_b)
        pred_label = 1.0 if score >= 0 else 0.0
        correct += int(pred_label == label)
    return correct / len(held) if held else 0.0


def fit(*, epochs: int = 80, seed: int = 20261006, copies: int = 2) -> TrainedWeights:
    vocab = build_vocab()
    weights, loss_start = train_sequencer(vocab, epochs=epochs, seed=seed, copies=copies)
    rows = _examples(vocab, 1, seed)
    safety = train_safety(weights)
    weights.metrics = TrainMetrics(
        loss_start, _mean_loss(weights, rows), _token_accuracy(weights, rows), safety
    )
    return weights


def _hex_array(values: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(values, dtype=np.float32)
    return {"shape": list(array.shape), "hex": array.tobytes().hex()}


def dump_model(weights: TrainedWeights) -> dict[str, Any]:
    return {
        "schema": "reverbscope.guided.local_model.v1",
        "model_id": MODEL_ID,
        "license": "Apache-2.0",
        "catalog_fingerprint": weights.vocab.fingerprint,
        "trained_on": "catalog-only",
        "network_used": False,
        "metrics": weights.metrics.to_dict(),
        "arrays": {
            "W1": _hex_array(weights.W1),
            "b1": _hex_array(weights.b1),
            "step": _hex_array(weights.step),
            "W_h": _hex_array(weights.W_h),
            "W_s": _hex_array(weights.W_s),
            "b": _hex_array(weights.b),
            "safety_w": _hex_array(weights.safety_w),
            "safety_b": _hex_array(np.asarray([weights.safety_b])),
        },
    }


def save_model(weights: TrainedWeights, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dump_model(weights)), encoding="utf-8")
    return path


def main() -> None:
    weights = fit()
    dest = Path(__file__).with_name("guided-clause-v1.json")
    save_model(weights, dest)


if __name__ == "__main__":
    main()
