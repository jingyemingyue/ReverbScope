"""Training corpus for the on-device explanation model.

Built only from the offline catalog. No measurement, no audio, no network.
The decoder may emit a catalog sentence. It has no way to emit a new number.
"""

from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass

import numpy as np

from reverbscope.experimental.guided.catalog import resolve_copy
from reverbscope.experimental.guided.findings import (
    Confidence,
    FindingType,
    Priority,
    StructuredFinding,
    ValidityState,
)

MODEL_ID = "guided-clause-v1"
LICENSE_NAME = "Apache-2.0"
TRAINED_LANGUAGES = ("en", "zh-CN")
LENGTHS = ("concise", "balanced", "detailed")
HASH_DIM = 256
SAFETY_DIM = HASH_DIM + 1
MAX_LEN = 10

# Appended only to unsafe training rows. Never stored as an explanation.
POISON_SUFFIXES = (
    " The delay is 12.5 ms.",
    " T30 approximately 0.72 s.",
    " This is the desk.",
    "就是桌面造成的。",
    " Please lift the safety ground.",
    "请断开地线。",
    " B is better overall.",
    " confidence is low.",
    " STI is 0.5.",
)

EXPERTISE = ("beginner", "intermediate", "expert")
VALIDITY = tuple(item.value for item in ValidityState)
CONFIDENCE = tuple(item.value for item in Confidence)
PRIORITY = tuple(item.value for item in Priority)
_ROLE_ORDER = ("what", "why", "impact", "action", "verify")
_LENGTH_ROLES = {
    "concise": ("what", "action"),
    "balanced": ("what", "why", "action", "verify"),
    "detailed": ("what", "why", "impact", "cause:0", "cause:1", "action", "verify"),
}


@dataclass(frozen=True)
class Clause:
    kind: str
    language: str
    role: str
    text: str


@dataclass(frozen=True)
class Vocab:
    clauses: tuple[Clause, ...]
    fingerprint: str

    @property
    def stop_id(self) -> int:
        return len(self.clauses)

    @property
    def size(self) -> int:
        return len(self.clauses) + 1


def _roles(kind: FindingType, language: str) -> tuple[tuple[str, str], ...]:
    copy = resolve_copy(kind, language).copy
    found = [(role, getattr(copy, role)) for role in _ROLE_ORDER]
    found.extend((f"cause:{index}", text) for index, text in enumerate(copy.causes))
    return tuple((role, text) for role, text in found if text)


def build_vocab() -> Vocab:
    clauses: list[Clause] = []
    for kind in FindingType:
        for language in TRAINED_LANGUAGES:
            for role, text in _roles(kind, language):
                clauses.append(Clause(kind.value, language, role, text))
    payload = "\n".join(f"{item.kind}|{item.language}|{item.role}|{item.text}" for item in clauses)
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return Vocab(tuple(clauses), fingerprint)


def feature_dim() -> int:
    return (
        len(FindingType)
        + len(TRAINED_LANGUAGES)
        + len(EXPERTISE)
        + len(LENGTHS)
        + len(VALIDITY)
        + len(CONFIDENCE)
        + len(PRIORITY)
    )


def _one_hot(value: str, choices: tuple[str, ...]) -> list[float]:
    return [1.0 if value == item else 0.0 for item in choices]


def featurize(
    kind: str,
    language: str,
    expertise: str,
    length: str,
    validity: str,
    confidence: str,
    priority: str,
) -> np.ndarray:
    lang = language if language in TRAINED_LANGUAGES else "en"
    values = (
        _one_hot(kind, tuple(item.value for item in FindingType))
        + _one_hot(lang, TRAINED_LANGUAGES)
        + _one_hot(expertise, EXPERTISE)
        + _one_hot(length, LENGTHS)
        + _one_hot(validity, VALIDITY)
        + _one_hot(confidence, CONFIDENCE)
        + _one_hot(priority, PRIORITY)
    )
    return np.asarray(values, dtype=np.float64)


def target_ids(vocab: Vocab, kind: str, language: str, length: str) -> tuple[int, ...]:
    """Approved clause ids, then STOP. Length chooses the plan; type does not change."""
    by_role = {
        clause.role: index
        for index, clause in enumerate(vocab.clauses)
        if clause.kind == kind and clause.language == language
    }
    chosen = [by_role[role] for role in _LENGTH_ROLES[length] if role in by_role]
    ids = [*chosen, vocab.stop_id]
    if len(ids) > MAX_LEN:
        ids = [*ids[: MAX_LEN - 1], vocab.stop_id]
    return tuple(ids)


def allowed_mask(vocab: Vocab, kind: str, language: str) -> np.ndarray:
    lang = language if language in TRAINED_LANGUAGES else "en"
    mask = np.zeros(vocab.size, dtype=bool)
    for index, clause in enumerate(vocab.clauses):
        if clause.kind == kind and clause.language == lang:
            mask[index] = True
    mask[vocab.stop_id] = True
    return mask


def hash_text(text: str, dim: int = HASH_DIM) -> np.ndarray:
    """Stable character trigrams. ``hash()`` is not used; it changes per process."""
    vec = np.zeros(dim, dtype=np.float64)
    raw = text.lower()
    if len(raw) < 3:
        raw = f"{raw}   "
    for index in range(len(raw) - 2):
        gram = raw[index : index + 3].encode("utf-8")
        hashed = zlib.crc32(gram)
        vec[hashed % dim] += 1.0 if hashed % 2 == 0 else -1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def safety_features(text: str) -> np.ndarray:
    """Trigram hash plus one bit: any digit. Explanations are not allowed to carry one."""
    base = hash_text(text, HASH_DIM)
    digit = 4.0 if any(character.isdigit() for character in text) else 0.0
    return np.concatenate((base, np.asarray([digit], dtype=np.float64)))


def finding_features(
    finding: StructuredFinding, language: str, length: str, expertise: str
) -> np.ndarray:
    return featurize(
        finding.type.value,
        language,
        expertise,
        length,
        finding.validity.value,
        finding.confidence.value,
        finding.priority.value,
    )


def canonical_text(vocab: Vocab, kind: str, language: str, length: str) -> str:
    lang = language if language in TRAINED_LANGUAGES else "en"
    ids = target_ids(vocab, kind, lang, length)
    parts = [vocab.clauses[item].text for item in ids if item != vocab.stop_id]
    if lang == "zh-CN":
        return "".join(parts)
    return " ".join(parts)
