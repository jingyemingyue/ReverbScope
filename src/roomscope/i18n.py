"""gettext setup, locale selection and ``_()``.

Catalogs live in ``src/roomscope/locale/<lang>/LC_MESSAGES/roomscope.po``.
``.mo`` files are compiled by the Hatch build hook into the wheel only; they
are not committed and RoomScope never writes one at run time (an installed
package tree or a frozen bundle may be read-only, and a write there would be
an untracked side effect). English is the source language and needs no
catalog.

Loading: a ``.mo`` is used when it was compiled from the ``.po`` next to it
(the compiler records the ``.po``'s SHA-256 in the ``.mo`` header); otherwise
the ``.po`` is parsed in memory. A ``.mo`` without a ``.po`` beside it is used
as is.

Selection order (ARCHITECTURE_V1.md §5.6): ``--lang``, ``settings.language``,
``ROOMSCOPE_LANG``, the system locale; English when nothing matches.
"""

from __future__ import annotations

import gettext
import hashlib
import locale as py_locale
import os
import re
import string
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DOMAIN = "roomscope"
ENV_LANG = "ROOMSCOPE_LANG"
DEFAULT_LANG = "en"

_LOCALE_DIR = Path(__file__).resolve().parent / "locale"
#: ``.mo`` header field that names the SHA-256 of the ``.po`` it was compiled from.
SOURCE_HASH_HEADER = "X-RoomScope-Source-SHA256"
#: gettext's separator between a message context and its msgid.
_CONTEXT_SEPARATOR = "\x04"
#: Catalog directory names other than English and the two Chinese variants.
#: Regional tags (``ja_JP``, ``es_MX``) map onto these.
_LANGUAGE_CATALOGS = frozenset({"de", "es", "fr", "ja", "ko"})
_current = DEFAULT_LANG
_translation: gettext.NullTranslations = gettext.NullTranslations()


def locale_dir() -> Path:
    return _LOCALE_DIR


def current_locale() -> str:
    return _current


def available_locales() -> list[str]:
    """Locales that have a catalog, plus English (the source language)."""
    found = {DEFAULT_LANG}
    if _LOCALE_DIR.is_dir():
        for child in _LOCALE_DIR.iterdir():
            messages = child / "LC_MESSAGES"
            if (messages / f"{DOMAIN}.mo").is_file() or (messages / f"{DOMAIN}.po").is_file():
                found.add(child.name)
    return sorted(found)


def normalize_lang(tag: str | None) -> str:
    """Map a BCP-47 / locale tag onto a catalog directory name."""
    if not tag:
        return DEFAULT_LANG
    raw = tag.strip().replace("-", "_")
    if not raw:
        return DEFAULT_LANG
    lower = raw.lower()
    if lower in {"c", "posix"}:
        return DEFAULT_LANG
    # zh, zh_CN, zh-Hans, zh-Hans-CN (macOS / Qt uiLanguages), zh_CHS, zh_SG and
    # Windows' getlocale() form "Chinese (Simplified)_China" all mean Simplified.
    if lower in {"zh", "zh_cn", "zh_hans", "zh_sg", "zh_chs"} or lower.startswith(
        ("zh_hans", "chinese (simplified)", "chinese_simplified")
    ):
        return "zh_CN"
    # zh_TW, zh-Hant, zh_HK, zh_MO and Windows "Chinese (Traditional)" → zh_TW.
    if lower in {"zh_tw", "zh_hk", "zh_mo", "zh_hant", "zh_cht"} or lower.startswith(
        ("zh_hant", "chinese (traditional)", "chinese_traditional")
    ):
        return "zh_TW"
    if "_" in raw:
        lang, _, region = raw.partition("_")
        lang = lang.lower()
        if lang in _LANGUAGE_CATALOGS:
            return lang
        return f"{lang}_{region.upper()}" if region else lang
    if lower in _LANGUAGE_CATALOGS:
        return lower
    return raw.lower()


def resolve_language(
    explicit: str | None = None, *, system_languages: Sequence[str] | None = None
) -> str:
    """Pick a language without activating it.

    ``system_languages`` are the desktop's preferred UI languages (the GUI
    passes Qt's ``QLocale.system().uiLanguages()``); they stand for the
    system locale when no locale variable is set, as on macOS when the app is
    opened from the Finder.
    """
    if explicit:
        return normalize_lang(explicit)
    try:
        from roomscope.settings import load_settings

        configured = load_settings().language
    except Exception:
        configured = ""
    if configured:
        return normalize_lang(configured)
    env = os.environ.get(ENV_LANG)
    if env:
        return normalize_lang(env)
    return _system_language(system_languages)


def activate(lang: str | None = None, *, system_languages: Sequence[str] | None = None) -> str:
    """Install the catalog for ``lang`` (resolved if omitted) and return it.

    ``lang is None`` follows the selection order. Pass ``"en"`` to force English.
    """
    global _current, _translation
    chosen = (
        resolve_language(None, system_languages=system_languages)
        if lang is None
        else normalize_lang(lang)
    )
    loaded = _load_translation(chosen)
    if chosen != DEFAULT_LANG and _is_null(loaded):
        chosen = DEFAULT_LANG
        loaded = gettext.NullTranslations()
    _translation = loaded
    _current = chosen
    return _current


def _(message: str) -> str:
    """Translate ``message``. Named placeholders are expanded by the caller."""
    return _translation.gettext(message)


def N_(message: str) -> str:  # noqa: N802 - the gettext convention for a deferred marker
    """Mark ``message`` for extraction without translating it now.

    Used for module-level constants that are translated where they are shown
    (``_(SAFETY_MESSAGE)``), so extractors and the catalog-completeness test
    still see the literal.
    """
    return message


def pgettext(context: str, message: str) -> str:
    """Translate a short ``message`` whose meaning depends on ``context``.

    Single words that are inserted into a sentence ("long", "tail") need a
    context so that the same English word used elsewhere can be translated
    differently.
    """
    return _translation.pgettext(context, message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def format_message(template: str, **params: Any) -> str:
    """gettext + ``str.format`` with ASCII digits (never locale-aware numbers)."""
    return _(template).format(**params)


#: Message context of the stored English diagnostics (notes, warnings,
#: reasons) that :func:`localize` shows in the active language.
DIAGNOSTIC_CONTEXT = "diagnostic"
_FIELD = re.compile(r"\{(\w+)(![rsa])?(:[^{}]*)?\}")
#: Format types whose value is a number; such a field matches only a number.
_NUMERIC_TYPES = frozenset("bcdeEfFgGnoxX%")
_NUMBER = r" *(?:[-+]?(?:\d[\d,_]*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf))%?"
_diagnostic_patterns: tuple[int, list[tuple[re.Pattern[str], re.Pattern[str], str]]] | None = None


def diag(template: str, **params: Any) -> str:
    """English text of a diagnostic that a result file stores.

    Notes, warnings and reasons stay English in ``result.json`` so a file
    reads the same in every language and keeps its schema. The ``template`` is
    extracted into the catalog under the ``"diagnostic"`` context, and
    :func:`localize` recognises the stored sentence when it is displayed.
    """
    return template.format(**params) if params else template


def _template_pattern(template: str, *, strict: bool = True) -> re.Pattern[str]:
    parts: list[str] = []
    seen: set[str] = set()
    for literal, field, spec, _conversion in string.Formatter().parse(template):
        parts.append(re.escape(literal))
        if field is None:
            continue
        if field in seen:
            parts.append(f"(?P={field})")
        elif spec and spec[-1] in _NUMERIC_TYPES:
            # A number formatted as the template says: text never fills it.
            seen.add(field)
            parts.append(f"(?P<{field}>{_NUMBER})")
        else:
            seen.add(field)
            # Strict: a value never spans the "; " that joins several
            # diagnostics. The loose form lets a value be a whole nested
            # diagnostic that has a "; " of its own.
            parts.append(f"(?P<{field}>(?:(?!; ).)+?)" if strict else f"(?P<{field}>.+?)")
    return re.compile("".join(parts), re.DOTALL)


def _patterns() -> list[tuple[re.Pattern[str], re.Pattern[str], str]]:
    """(strict and loose English patterns, translation without format specs),
    most specific first."""
    global _diagnostic_patterns
    if _diagnostic_patterns is not None and _diagnostic_patterns[0] == id(_translation):
        return _diagnostic_patterns[1]
    catalog: dict[str, str] = getattr(_translation, "_catalog", {}) or {}
    prefix = f"{DIAGNOSTIC_CONTEXT}{_CONTEXT_SEPARATOR}"
    entries: list[tuple[int, re.Pattern[str], re.Pattern[str], str]] = []
    for key, translated in catalog.items():
        if not isinstance(key, str) or not key.startswith(prefix) or not translated:
            continue
        template = key[len(prefix) :]
        literal = sum(len(text) for text, *_rest in string.Formatter().parse(template))
        plain = _FIELD.sub(lambda m: "{" + m.group(1) + "}", translated)
        strict = _template_pattern(template)
        loose = _template_pattern(template, strict=False)
        entries.append((literal, strict, loose, plain))
    entries.sort(key=lambda entry: -entry[0])
    patterns = [(strict, loose, plain) for _literal, strict, loose, plain in entries]
    _diagnostic_patterns = (id(_translation), patterns)
    return patterns


def localize(text: str, _depth: int = 0) -> str:
    """Show a stored English diagnostic in the active language.

    Several diagnostics joined with ``"; "`` are shown one by one. Text that
    matches no catalogued template (a diagnostic from another version, a file
    path, an OS error) is returned unchanged.
    """
    if not text or _current == DEFAULT_LANG or _depth > 2:
        return text
    patterns = _patterns()
    for strict, _loose, translated in patterns:
        match = strict.fullmatch(text)
        if match is not None:
            return _fill(translated, match, text, _depth)
    if "; " in text:
        # A nested diagnostic with a "; " of its own, recognised as a whole
        # (never a value that is only a join of several diagnostics: the
        # "; " would then belong to the outer text).
        for _strict, loose, translated in patterns:
            match = loose.fullmatch(text)
            if match is not None and all(
                "; " not in value or _whole(value, _depth + 1) is not None
                for value in match.groupdict().values()
            ):
                return _fill(translated, match, text, _depth)
        pieces = text.split("; ")
        parts = [localize(part, _depth) for part in pieces]
        # Nothing recognised: the stored text as it is, separators included.
        return text if parts == pieces else "；".join(parts)
    return text


def _whole(text: str, depth: int) -> str | None:
    """The translation of ``text`` when one template matches all of it."""
    if depth > 2:
        return None
    for strict, _loose, translated in _patterns():
        match = strict.fullmatch(text)
        if match is not None:
            return _fill(translated, match, text, depth)
    return None


def _fill(translated: str, match: re.Match[str], text: str, depth: int) -> str:
    values = {k: _localize_value(v, depth + 1) for k, v in match.groupdict().items()}
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


def _localize_value(value: str, depth: int) -> str:
    """A value inside a diagnostic: a nested diagnostic, or a stored word
    such as a validity (``not_computed``) or a confidence (``high``)."""
    nested = localize(value, depth)
    if nested != value:
        return nested
    if " or " in value:
        # Alternatives listed in a stored sentence ("1.20 m or 1.35 m").
        return (
            _("{a} or {b}")
            .format(a="", b="")
            .join(_localize_value(part, depth) for part in value.split(" or "))
        )
    for candidate in (value, value.replace("_", " ")):
        translated = _translation.gettext(candidate)
        if translated != candidate:
            return translated
    return value


def parse_po(path: Path) -> dict[str, str]:
    """Parse a gettext ``.po`` file into msgid → msgstr (empty msgstr skipped).

    An entry with a ``msgctxt`` is keyed ``"<context>\\x04<msgid>"``, the
    form :meth:`gettext.GNUTranslations.pgettext` looks up.
    """
    catalog: dict[str, str] = {}
    msgctxt = ""
    msgid = ""
    msgstr = ""
    collecting: str | None = None

    def _commit() -> None:
        nonlocal msgctxt, msgid, msgstr
        if msgid and msgstr:
            key = f"{msgctxt}{_CONTEXT_SEPARATOR}{msgid}" if msgctxt else msgid
            catalog[key] = msgstr
        msgctxt = ""
        msgid = ""
        msgstr = ""

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgctxt "):
            _commit()
            collecting = "ctxt"
            msgctxt = _unquote(line[8:])
            continue
        if line.startswith("msgid "):
            if collecting != "ctxt":
                _commit()
            collecting = "id"
            msgid = _unquote(line[6:])
            msgstr = ""
            continue
        if line.startswith("msgstr "):
            collecting = "str"
            msgstr = _unquote(line[7:])
            continue
        if line.startswith('"') and collecting == "ctxt":
            msgctxt += _unquote(line)
        elif line.startswith('"') and collecting == "id":
            msgid += _unquote(line)
        elif line.startswith('"') and collecting == "str":
            msgstr += _unquote(line)
    _commit()
    catalog.pop("", None)
    return catalog


def source_hash(po: Path) -> str:
    """SHA-256 of a ``.po`` file's bytes, as recorded in a compiled ``.mo``."""
    return hashlib.sha256(po.read_bytes()).hexdigest()


def write_mo(catalog: dict[str, str], path: Path, *, source_sha256: str | None = None) -> None:
    """Write a GNU ``.mo`` file that :class:`gettext.GNUTranslations` can read."""
    # Header (required by gettext)
    header = "Content-Type: text/plain; charset=UTF-8\n"
    if source_sha256:
        header += f"{SOURCE_HASH_HEADER}: {source_sha256}\n"
    entries = {"": header, **catalog}
    keys = sorted(entries)
    encoded = [(key.encode("utf-8"), entries[key].encode("utf-8")) for key in keys]
    key_start = 28 + 16 * len(encoded)
    value_start = key_start + sum(len(k) + 1 for k, _ in encoded)
    key_offsets: list[tuple[int, int]] = []
    value_offsets: list[tuple[int, int]] = []
    offset = key_start
    for key, _ in encoded:
        key_offsets.append((len(key), offset))
        offset += len(key) + 1
    offset = value_start
    for _, value in encoded:
        value_offsets.append((len(value), offset))
        offset += len(value) + 1

    count = len(encoded)
    buf = bytearray()
    buf += struct.pack("<Iiiiiii", 0x950412DE, 0, count, 28, 28 + 8 * count, 0, 0)
    for length, off in key_offsets:
        buf += struct.pack("<II", length, off)
    for length, off in value_offsets:
        buf += struct.pack("<II", length, off)
    for key, _ in encoded:
        buf += key + b"\x00"
    for _, value in encoded:
        buf += value + b"\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def compile_catalogs(root: Path | None = None, out_dir: Path | None = None) -> list[Path]:
    """Compile every ``<lang>/LC_MESSAGES/roomscope.po`` under ``root``.

    The ``.mo`` files go to the same relative path under ``out_dir`` (next to
    each ``.po`` when ``out_dir`` is omitted) and record the ``.po``'s SHA-256
    so that a stale ``.mo`` is never preferred over an edited ``.po``.
    """
    base = root or _LOCALE_DIR
    written: list[Path] = []
    if not base.is_dir():
        return written
    for po in sorted(base.glob(f"*/LC_MESSAGES/{DOMAIN}.po")):
        target_root = out_dir if out_dir is not None else base
        mo = target_root / po.relative_to(base).with_suffix(".mo")
        write_mo(parse_po(po), mo, source_sha256=source_hash(po))
        written.append(mo)
    return written


def _system_language(system_languages: Sequence[str] | None = None) -> str:
    for candidate in (
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
    ):
        if candidate:
            tag = candidate.split(".", 1)[0]
            if tag and tag.upper() not in {"C", "POSIX"}:
                return normalize_lang(tag)
    if system_languages:
        known = available_locales()
        for tag in system_languages:
            lang = normalize_lang(tag)
            if lang in known:
                return lang
            if lang.split("_", 1)[0] == DEFAULT_LANG:
                return DEFAULT_LANG
    windows = _windows_ui_language()
    if windows:
        return normalize_lang(windows)
    try:
        detected = py_locale.getlocale()[0]
    except (ValueError, TypeError):
        detected = None
    if detected:
        return normalize_lang(detected)
    return DEFAULT_LANG


def _windows_ui_language() -> str | None:
    """The Windows display language (``GetUserDefaultUILanguage``), e.g. ``zh_CN``.

    Windows sets no ``LANG``; the display language is the user's choice, and
    ``locale.windows_locale`` maps its language identifier to a locale name.
    ``ctypes.windll`` exists on Windows only.
    """
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        lang_id = int(windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError, ValueError):
        return None
    name = py_locale.windows_locale.get(lang_id)
    return str(name) if name else None


def _load_translation(lang: str) -> gettext.NullTranslations:
    """Load the catalog for ``lang`` without writing anything to disk."""
    if lang == DEFAULT_LANG:
        return gettext.NullTranslations()
    messages = _LOCALE_DIR / lang / "LC_MESSAGES"
    mo = messages / f"{DOMAIN}.mo"
    po = messages / f"{DOMAIN}.po"
    if mo.is_file():
        try:
            with mo.open("rb") as handle:
                compiled = gettext.GNUTranslations(handle)
        except (OSError, struct.error, UnicodeDecodeError):
            compiled = None
        if compiled is not None:
            if not po.is_file():
                return compiled
            recorded = compiled.info().get(SOURCE_HASH_HEADER.lower())
            if recorded == source_hash(po):
                return compiled
    if po.is_file():
        return _PoTranslations(parse_po(po))
    return gettext.NullTranslations()


def _is_null(translation: gettext.NullTranslations) -> bool:
    return translation.__class__ is gettext.NullTranslations


def _unquote(fragment: str) -> str:
    text = fragment.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text.replace(r"\n", "\n").replace(r"\t", "\t").replace(r"\"", '"').replace(r"\\", "\\")


class _PoTranslations(gettext.NullTranslations):
    """In-memory catalog parsed from a ``.po`` (no compiled ``.mo`` matches it)."""

    def __init__(self, catalog: dict[str, str]) -> None:
        super().__init__()
        self._catalog = catalog

    def gettext(self, message: str) -> str:
        return self._catalog.get(message, message)

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return self.gettext(msgid1 if n == 1 else msgid2)

    def pgettext(self, context: str, message: str) -> str:
        return self._catalog.get(f"{context}{_CONTEXT_SEPARATOR}{message}", message)
