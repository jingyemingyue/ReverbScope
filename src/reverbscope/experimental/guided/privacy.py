"""Network boundary, secret redaction, and credential storage.

Keys stay on the device. They are never written to settings, sessions,
telemetry, logs, or a crash report by this module.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib import error, request

log = logging.getLogger("reverbscope.experimental.guided.privacy")

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?\S+"),
    re.compile(r"(?i)(x-api-key\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(x-goog-api-key\s*[:=]\s*)\S+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret)\s*[:=]\s*)\S+"),
    re.compile(r"(?i)\bBearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{6,}\b"),
)


class SecretRedactor:
    """Strip credentials from text before it is logged or shown."""

    def redact(self, text: str) -> str:
        cleaned = text
        for pattern in _SECRET_PATTERNS:
            cleaned = pattern.sub(r"\1[redacted]" if pattern.groups else "[redacted]", cleaned)
        return cleaned


REDACTOR = SecretRedactor()


class Purpose(StrEnum):
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    LOCAL_MODEL_DOWNLOAD = "local_model_download"
    KNOWLEDGE_PACK_DOWNLOAD = "knowledge_pack_download"
    CLOUD_AI = "cloud_ai"
    UPDATE_CHECK = "update_check"
    TELEMETRY = "telemetry"
    CRASH_REPORT = "crash_report"


@dataclass
class NetworkPolicy:
    """Every external call asks this first. Defaults are closed."""

    privacy_mode: bool = False
    offline: bool = False
    allow_knowledge_lookup: bool = False
    allow_model_download: bool = False
    allow_pack_download: bool = False
    allow_cloud_ai: bool = False
    allow_update_check: bool = False
    allow_telemetry: bool = False
    allow_crash_report: bool = False

    def allows(self, purpose: Purpose) -> bool:
        if self.privacy_mode or self.offline:
            return False
        flags = {
            Purpose.KNOWLEDGE_LOOKUP: self.allow_knowledge_lookup,
            Purpose.LOCAL_MODEL_DOWNLOAD: self.allow_model_download,
            Purpose.KNOWLEDGE_PACK_DOWNLOAD: self.allow_pack_download,
            Purpose.CLOUD_AI: self.allow_cloud_ai,
            Purpose.UPDATE_CHECK: self.allow_update_check,
            Purpose.TELEMETRY: self.allow_telemetry,
            Purpose.CRASH_REPORT: self.allow_crash_report,
        }
        return flags[purpose]

    def denial_reason(self, purpose: Purpose) -> str:
        if self.privacy_mode:
            return "privacy_mode"
        if self.offline:
            return "offline"
        return f"permission_off:{purpose.value}"


class NetworkDeniedError(Exception):
    def __init__(self, purpose: str, reason: str) -> None:
        super().__init__(f"{purpose} denied: {reason}")
        self.purpose = purpose
        self.reason = reason


class NetworkError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(REDACTOR.redact(message))
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, object]
    text: str


class HttpTransport(Protocol):
    def request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, object] | None,
        timeout_s: float,
    ) -> HttpResponse: ...


class UrllibTransport:
    """Real transport. Callers must already have passed NetworkPolicy."""

    def request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, object] | None,
        timeout_s: float,
    ) -> HttpResponse:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = int(response.status)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise NetworkError(REDACTOR.redact(raw or str(exc)), status=exc.code) from None
        except error.URLError as exc:
            raise NetworkError(REDACTOR.redact(str(exc.reason))) from None
        parsed: dict[str, object]
        try:
            loaded = json.loads(raw) if raw else {}
            parsed = loaded if isinstance(loaded, dict) else {"value": loaded}
        except ValueError:
            parsed = {}
        return HttpResponse(status=status, body=parsed, text=raw)


class NetworkClient:
    def __init__(self, policy: NetworkPolicy, transport: HttpTransport | None = None) -> None:
        self.policy = policy
        self.transport = transport if transport is not None else UrllibTransport()

    def request_json(
        self,
        purpose: Purpose,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, object] | None,
        timeout_s: float,
    ) -> HttpResponse:
        if not self.policy.allows(purpose):
            raise NetworkDeniedError(purpose.value, self.policy.denial_reason(purpose))
        try:
            response = self.transport.request_json(method, url, headers, body, timeout_s)
        except NetworkError:
            raise
        except Exception as exc:
            log.info(
                "network failure purpose=%s status_class=error",
                purpose.value,
            )
            raise NetworkError(REDACTOR.redact(str(exc))) from None
        log.info(
            "network purpose=%s status_class=%s",
            purpose.value,
            response.status // 100,
        )
        return response


class StoreChoice(StrEnum):
    SECURE = "secure"
    SESSION = "session"
    CANCEL = "cancel"


@dataclass
class StoreResult:
    stored: bool
    where: str
    message: str


class CredentialStore(Protocol):
    def available(self) -> bool: ...

    def set_key(self, account: str, key: str) -> None: ...

    def get_key(self, account: str) -> str | None: ...

    def delete_key(self, account: str) -> None: ...


class MemoryCredentialStore:
    """Process memory only. Nothing is written to disk."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def available(self) -> bool:
        return True

    def set_key(self, account: str, key: str) -> None:
        self._keys[account] = key

    def get_key(self, account: str) -> str | None:
        return self._keys.get(account)

    def delete_key(self, account: str) -> None:
        self._keys.pop(account, None)


class KeyringCredentialStore:
    """System keyring when the optional ``keyring`` package can actually open one."""

    service_name = "reverbscope.guided"

    def available(self) -> bool:
        module = _keyring_module()
        if module is None:
            return False
        getter = getattr(module, "get_keyring", None)
        if not callable(getter):
            return False
        try:
            backend = getter()
        except Exception:
            return False
        name = type(backend).__name__.lower()
        return "fail" not in name and "null" not in name

    def set_key(self, account: str, key: str) -> None:
        module = _keyring_module()
        if module is None or not self.available():
            raise OSError("secure credential storage is unavailable")
        setter = getattr(module, "set_password", None)
        if not callable(setter):
            raise OSError("secure credential storage is unavailable")
        setter(self.service_name, account, key)

    def get_key(self, account: str) -> str | None:
        module = _keyring_module()
        if module is None or not self.available():
            return None
        getter = getattr(module, "get_password", None)
        if not callable(getter):
            return None
        found = getter(self.service_name, account)
        return str(found) if isinstance(found, str) and found else None

    def delete_key(self, account: str) -> None:
        module = _keyring_module()
        if module is None or not self.available():
            return
        deleter = getattr(module, "delete_password", None)
        if not callable(deleter):
            return
        try:
            deleter(self.service_name, account)
        except Exception:
            return


def _keyring_module() -> object | None:
    try:
        return importlib.import_module("keyring")
    except ImportError:
        return None


@dataclass
class CredentialVault:
    """Session memory plus an optional system store. Never a JSON file."""

    memory: MemoryCredentialStore = field(default_factory=MemoryCredentialStore)
    keyring: KeyringCredentialStore = field(default_factory=KeyringCredentialStore)
    _session_accounts: set[str] = field(default_factory=set)

    def secure_available(self) -> bool:
        return self.keyring.available()

    def configured(self, account: str) -> bool:
        return self.get(account) is not None

    def get(self, account: str) -> str | None:
        if account in self._session_accounts:
            return self.memory.get_key(account)
        return self.keyring.get_key(account)

    def store(self, account: str, key: str, choice: StoreChoice) -> StoreResult:
        if choice is StoreChoice.CANCEL or not key:
            return StoreResult(False, "cancelled", "The key was not stored.")
        if choice is StoreChoice.SESSION:
            self.memory.set_key(account, key)
            self._session_accounts.add(account)
            return StoreResult(True, "session", "The key is kept for this session only.")
        if not self.secure_available():
            return StoreResult(
                False,
                "unavailable",
                "Secure credential storage is unavailable. "
                "Choose session-only or cancel. The key was not written to a file.",
            )
        self.keyring.set_key(account, key)
        self._session_accounts.discard(account)
        self.memory.delete_key(account)
        return StoreResult(True, "secure", "The key was stored in the system credential store.")

    def remove(self, account: str) -> None:
        self.memory.delete_key(account)
        self._session_accounts.discard(account)
        self.keyring.delete_key(account)


def mask_key(_key: str | None) -> str:
    """Default display. No tail, no full key."""
    if not _key:
        return ""
    return "••••••••••••••••"


def reveal_key(key: str, *, confirmed: bool) -> str:
    """A second, explicit confirmation. The normal UI must not call this."""
    if not confirmed:
        raise PermissionError("showing a key requires an explicit confirmation")
    return key


DEFAULT_KEY_ACTIONS = ("replace", "remove", "test_connection")

_PROCESS_VAULT: CredentialVault | None = None


def process_vault() -> CredentialVault:
    """One vault for this process. Session keys survive from settings to a later explanation.

    Tests that need isolation should construct ``CredentialVault()`` themselves.
    """
    global _PROCESS_VAULT
    if _PROCESS_VAULT is None:
        _PROCESS_VAULT = CredentialVault()
    return _PROCESS_VAULT
