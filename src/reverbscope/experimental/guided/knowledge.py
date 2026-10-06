"""Optional local models and knowledge packs. Nothing is downloaded by default.

Online lookup is a separate capability from cloud explanation. It sends a
sanitized topic, never a measurement, and only when that permission is on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from reverbscope.experimental.guided.context import sanitize_public_query
from reverbscope.experimental.guided.findings import FindingType
from reverbscope.experimental.guided.privacy import NetworkClient, NetworkDeniedError, Purpose

SOURCE_RANK = (
    "reverbscope_official",
    "daw_vendor",
    "hardware_vendor",
    "technical_reference",
    "public_source",
    "community_report",
)


@dataclass(frozen=True)
class LocalModelManifest:
    model_id: str
    size_bytes: int
    license_name: str
    sha256: str
    path: Path | None = None

    @property
    def installed(self) -> bool:
        return self.path is not None and self.path.is_file()


@dataclass(frozen=True)
class KnowledgePack:
    pack_id: str
    title: str
    size_bytes: int
    sha256: str
    path: Path | None = None

    @property
    def installed(self) -> bool:
        return self.path is not None and self.path.is_file()


CORE_PACK = KnowledgePack(
    pack_id="core-acoustic",
    title="Core Acoustic Knowledge",
    size_bytes=0,
    sha256="",
)
DAW_PACK = KnowledgePack(
    pack_id="daw",
    title="DAW Knowledge Pack",
    size_bytes=0,
    sha256="",
)
HARDWARE_PACK = KnowledgePack(
    pack_id="hardware",
    title="Hardware Compatibility Pack",
    size_bytes=0,
    sha256="",
)

#: Sizes are unknown until a real file is published. The default is not installed.
KNOWN_PACKS = (CORE_PACK, DAW_PACK, HARDWARE_PACK)

_QUERIES = {
    FindingType.SAMPLE_RATE_MISMATCH: "DAW import sample rate conversion official documentation",
    FindingType.TIME_STRETCH_DETECTED: "DAW disable time stretch for a clip official documentation",
    FindingType.AUDIO_DROPOUT_DETECTED: "audio interface buffer size dropout official documentation",
    FindingType.DEVICE_TIMING_SUSPICIOUS: "audio interface shared clock official documentation",
    FindingType.MAINS_HUM_DETECTED: "mains hum grounding audio interface official documentation",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def verify_file(path: Path, expected: str) -> bool:
    if not expected or not path.is_file():
        return False
    return sha256_file(path) == expected.lower()


class LocalModelLibrary:
    """Tracks an optional model the user downloaded. Never downloads by itself."""

    def __init__(self, manifest: LocalModelManifest | None = None) -> None:
        self.manifest = manifest

    def available(self) -> bool:
        manifest = self.manifest
        if manifest is None or manifest.path is None:
            return False
        if not manifest.sha256:
            return False
        return verify_file(manifest.path, manifest.sha256)

    def describe(self) -> dict[str, object]:
        manifest = self.manifest
        if manifest is None:
            return {"installed": False, "model_id": None, "size_bytes": None, "license": None}
        return {
            "installed": self.available(),
            "model_id": manifest.model_id,
            "size_bytes": manifest.size_bytes,
            "license": manifest.license_name,
            "sha256_ok": self.available(),
        }

    def delete(self) -> bool:
        manifest = self.manifest
        if manifest is None or manifest.path is None or not manifest.path.is_file():
            return False
        manifest.path.unlink()
        return True


@dataclass(frozen=True)
class KnowledgeHit:
    query: str
    source_class: str
    community_report: bool
    text: str
    online: bool


class OnlineKnowledge:
    """Public-document lookup. Separate from cloud explanation.

    This build does not crawl the web by itself. A caller may supply an
    endpoint; the query is still only the sanitized topic.
    """

    def __init__(self, client: NetworkClient | None = None, endpoint: str | None = None) -> None:
        self.client = client
        self.endpoint = endpoint

    def lookup(self, kind: FindingType) -> KnowledgeHit:
        query = sanitize_public_query(_QUERIES.get(kind, kind.value.replace("_", " ")))
        if self.client is None or not self.client.policy.allows(Purpose.KNOWLEDGE_LOOKUP):
            reason = "offline_or_disabled"
            if self.client is not None:
                reason = self.client.policy.denial_reason(Purpose.KNOWLEDGE_LOOKUP)
            return KnowledgeHit(query, "reverbscope_official", False, reason, False)
        if not self.endpoint:
            return KnowledgeHit(
                query,
                "reverbscope_official",
                False,
                "online lookup is permitted, but no documentation endpoint is configured",
                False,
            )
        try:
            self.client.request_json(Purpose.KNOWLEDGE_LOOKUP, "GET", self.endpoint, {}, None, 5.0)
        except NetworkDeniedError:
            return KnowledgeHit(query, "reverbscope_official", False, "denied", False)
        return KnowledgeHit(query, "technical_reference", False, query, True)
