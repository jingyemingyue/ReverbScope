"""gettext setup, locale selection and ``_()``.

Catalogs live in ``src/reverbscope/locale/<lang>/LC_MESSAGES/reverbscope.po``.
``.mo`` files are compiled by the Hatch build hook into the wheel only; they
are not committed and ReverbScope never writes one at run time (an installed
package tree or a frozen bundle may be read-only, and a write there would be
an untracked side effect). English is the source language and needs no
catalog.

Loading: a ``.mo`` is used when it was compiled from the ``.po`` next to it
(the compiler records the ``.po``'s SHA-256 in the ``.mo`` header); otherwise
the ``.po`` is parsed in memory. A ``.mo`` without a ``.po`` beside it is used
as is.

Selection order (ARCHITECTURE_V1.md §5.6): ``--lang``, ``settings.language``
(``reverbscope config language``), ``REVERBSCOPE_LANG``, then the system's
language; English when nothing matches. The system's language is read where
the system keeps it:

* **macOS**: the user's preferred languages (``AppleLanguages`` in the global
  preferences, or Qt's ``uiLanguages`` in the GUI) before ``LC_ALL`` /
  ``LC_MESSAGES`` / ``LANG``. Terminal, iTerm and VS Code set
  ``LANG=en_US.UTF-8`` whatever the display language is.
* **Windows**: the display language (``GetUserDefaultUILanguage``) when it
  has a catalog or is English, then Qt's ``uiLanguages`` (GUI), then the
  POSIX variables, which only MSYS, Git Bash or Cygwin set.
* **Linux and other POSIX systems**: GNU ``LANGUAGE`` (a priority list such as
  ``zh_CN:en``, used as gettext uses it: only when the locale is not C or
  POSIX), then ``LC_ALL``, ``LC_MESSAGES``, ``LANG``, then the desktop's UI
  languages (GUI).

A preferred-language list counts its first entry that has a catalog or is
English.
"""

from __future__ import annotations

import gettext
import hashlib
import locale as py_locale
import os
import re
import string
import struct
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOMAIN = "reverbscope"
ENV_LANG = "REVERBSCOPE_LANG"
DEFAULT_LANG = "en"

_LOCALE_DIR = Path(__file__).resolve().parent / "locale"
#: ``.mo`` header field that names the SHA-256 of the ``.po`` it was compiled from.
SOURCE_HASH_HEADER = "X-ReverbScope-Source-SHA256"
#: gettext's separator between a message context and its msgid.
_CONTEXT_SEPARATOR = "\x04"
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
    if "_" in raw:
        lang, _, region = raw.partition("_")
        return f"{lang.lower()}_{region.upper()}" if region else lang.lower()
    return raw.lower()


#: Where the language in effect came from (:attr:`LanguageChoice.source`).
SOURCE_OPTION = "option"
SOURCE_SETTINGS = "settings"
SOURCE_ENVIRONMENT = "environment"
SOURCE_SYSTEM = "system"

#: Which system setting gave the language (:attr:`LanguageChoice.origin`).
ORIGIN_MACOS = "macos"
ORIGIN_WINDOWS = "windows"
ORIGIN_DESKTOP = "desktop"
ORIGIN_LOCALE = "locale"
#: ``LANGUAGE``, ``LC_ALL``, ``LC_MESSAGES`` and ``LANG`` are their own origins.
POSIX_VARIABLES = ("LC_ALL", "LC_MESSAGES", "LANG")

#: Display names of the languages, each written in its own language so that a
#: user finds theirs whatever the interface language is.
LANGUAGE_NAMES = {"en": "English", "zh_CN": "简体中文"}


@dataclass(frozen=True)
class LanguageChoice:
    """A language picked by the selection order, and why.

    ``source`` is one of the ``SOURCE_*`` constants. For the system's
    language, ``origin`` names the setting (``ORIGIN_*``, or the variable
    ``LANGUAGE`` / ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``) and ``value`` is
    what it held (``"zh-Hans-CN, en-CN"``, ``"zh_CN.UTF-8"``).
    """

    lang: str
    source: str
    origin: str = ""
    value: str = ""


def supported_language(tag: str | None) -> str | None:
    """``tag`` as a language ReverbScope has: a catalog, or English for any English.

    ``None`` for anything else (``fr_FR``, ``zh_TW``, ``C``). Encoding and
    modifier suffixes are ignored (``zh_CN.UTF-8``, ``de_DE@euro``).
    """
    if not tag or not tag.strip():
        return None
    base = tag.strip().split(".", 1)[0].split("@", 1)[0]
    if not base or base.upper() in {"C", "POSIX"}:
        return None
    lang = normalize_lang(base)
    if lang in available_locales():
        return lang
    if lang.split("_", 1)[0] == DEFAULT_LANG:
        return DEFAULT_LANG
    return None


def resolve_language(
    explicit: str | None = None, *, system_languages: Sequence[str] | None = None
) -> str:
    """Pick a language without activating it.

    ``system_languages`` are the desktop's preferred UI languages (the GUI
    passes Qt's ``QLocale.system().uiLanguages()``). On macOS they come
    first, as the Mac's own list does for the command line; elsewhere they
    stand for the system locale when no locale variable is set.
    """
    return language_choice(explicit, system_languages=system_languages).lang


def language_choice(
    explicit: str | None = None, *, system_languages: Sequence[str] | None = None
) -> LanguageChoice:
    """:func:`resolve_language`, with where the language came from."""
    if explicit:
        return LanguageChoice(normalize_lang(explicit), SOURCE_OPTION, value=explicit)
    try:
        from reverbscope.settings import load_settings

        configured = load_settings().language
    except Exception:
        configured = ""
    if configured:
        return LanguageChoice(normalize_lang(configured), SOURCE_SETTINGS, value=configured)
    env = os.environ.get(ENV_LANG)
    if env:
        return LanguageChoice(normalize_lang(env), SOURCE_ENVIRONMENT, ENV_LANG, env)
    lang, origin, value = _system_choice(system_languages)
    return LanguageChoice(lang, SOURCE_SYSTEM, origin, value)


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
    _shown.clear()
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


def list_separator() -> str:
    """What separates the items of a list: ``", "`` in English, ``"、"`` in Chinese."""
    return pgettext("list separator", ", ")


def list_join(items: Iterable[str]) -> str:
    """``items`` as a list in the active language (``zh_CN、en``)."""
    return list_separator().join(items)


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
    shown = _join(text, _depth, complete=False)
    # Nothing recognised: the stored text as it is, separators included.
    return text if shown is None else shown


def _segments(text: str) -> list[str]:
    """``text`` cut at each ``"; "`` outside parentheses.

    A ``"; "`` inside parentheses belongs to a nested value ("baseline
    unreliable (A; B)"), never to the join around it.
    """
    pieces: list[str] = []
    depth = start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == ";" and depth == 0 and text.startswith("; ", index):
            pieces.append(text[start:index])
            start = index + 2
    pieces.append(text[start:])
    return pieces


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return False
    return depth == 0


def _join(text: str, depth: int, *, complete: bool) -> str | None:
    """``text`` as diagnostics joined with ``"; "``, each shown translated.

    A template's own literal text may hold a ``"; "`` too ("...of the energy;
    limit 5 dB..."), so the longest run of pieces that one template matches
    wins. A piece that nothing matches stays English, or, when ``complete``,
    makes the whole text unrecognised. ``None`` when nothing was recognised.
    """
    pieces = _segments(text)
    shown: list[str] = []
    recognised = False
    start = 0
    while start < len(pieces):
        for stop in range(len(pieces), start, -1):
            translated = _one("; ".join(pieces[start:stop]), depth)
            if translated is not None:
                shown.append(translated)
                recognised = True
                start = stop
                break
        else:
            if complete:
                return None
            shown.append(pieces[start])
            start += 1
    return "；".join(shown) if recognised else None


#: Translations of whole diagnostics, per (text, depth), for the catalog
#: that :func:`activate` installed: long joined reasons are matched piece by
#: piece and every report shows the same reasons many times.
_shown: dict[tuple[str, int], str | None] = {}
_SHOWN_LIMIT = 4096


def _one(text: str, depth: int) -> str | None:
    """The translation of ``text`` when one template matches all of it."""
    if depth > 2:
        return None
    key = (text, depth)
    if key in _shown:
        return _shown[key]
    shown: str | None = None
    patterns = _patterns()
    for strict, _loose, translated in patterns:
        match = strict.fullmatch(text)
        if match is not None:
            shown = _fill(translated, match, text, depth)
            break
    else:
        if "; " in text:
            # A template whose value has a "; " of its own: a nested
            # diagnostic, or several joined, every one of them recognised.
            # An unbalanced value would take the "; " that joins the outer
            # text ("baseline unreliable (A); candidate ...").
            for _strict, loose, translated in patterns:
                match = loose.fullmatch(text)
                if match is not None and all(
                    "; " not in value
                    or (_balanced(value) and _join(value, depth + 1, complete=True) is not None)
                    for value in match.groupdict().values()
                ):
                    shown = _fill(translated, match, text, depth)
                    break
    if len(_shown) >= _SHOWN_LIMIT:
        _shown.clear()
    _shown[key] = shown
    return shown


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
        # Alternatives listed in a stored sentence ("1.20 m or 1.35 m"). An
        # error that says "or" ("Device or resource busy") is no list.
        parts = value.split(" or ")
        shown = [_localize_value(part, depth) for part in parts]
        if all(
            _MEASURE.fullmatch(part) or text != part
            for part, text in zip(parts, shown, strict=True)
        ):
            return _("{a} or {b}").format(a="", b="").join(shown)
    for candidate in (value, _STORED_WORDS.get(value, value.replace("_", " "))):
        translated = _translation.gettext(candidate)
        if translated != candidate:
            return translated
    return value


#: A measured value inside a stored sentence: "1.20 m", "-3.0 dB", "48000".
_MEASURE = re.compile(r"[-+]?\d[\d.,]*(?: ?[A-Za-z%]+)?")

#: Validity ids whose display word is worded differently. Comparison reasons
#: written by earlier versions held the id ("baseline outside_excitation_range").
_STORED_WORDS = {
    "insufficient_decay_range": N_("insufficient range"),
    "outside_excitation_range": N_("outside the sweep's range"),
}


def parse_po(path: Path) -> dict[str, str]:
    """Parse a gettext ``.po`` file into msgid → msgstr (empty msgstr skipped).

    An entry with a ``msgctxt`` is keyed ``"<context>\\x04<msgid>"``, the
    form :meth:`gettext.GNUTranslations.pgettext` looks up. An entry flagged
    ``#, fuzzy`` is skipped, as ``msgfmt`` skips it.
    """
    catalog: dict[str, str] = {}
    msgctxt = ""
    msgid = ""
    msgstr = ""
    collecting: str | None = None
    started = False
    fuzzy = False

    def _commit() -> None:
        nonlocal msgctxt, msgid, msgstr, started, fuzzy
        if msgid and msgstr and not fuzzy:
            key = f"{msgctxt}{_CONTEXT_SEPARATOR}{msgid}" if msgctxt else msgid
            catalog[key] = msgstr
        if started:
            fuzzy = False
        started = False
        msgctxt = ""
        msgid = ""
        msgstr = ""

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                _commit()  # the entry above is complete; the flag is for the next
                fuzzy = True
            continue
        if line.startswith("msgctxt "):
            _commit()
            started = True
            collecting = "ctxt"
            msgctxt = _unquote(line[8:])
            continue
        if line.startswith("msgid "):
            if collecting != "ctxt":
                _commit()
            started = True
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
    """Compile every ``<lang>/LC_MESSAGES/reverbscope.po`` under ``root``.

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
    """The system's language (the last step of the selection order)."""
    return _system_choice(system_languages)[0]


#: One step of the system's language: ``(language, origin, value)`` or ``None``.
_Step = Callable[[], tuple[str, str, str] | None]


def _system_choice(system_languages: Sequence[str] | None = None) -> tuple[str, str, str]:
    """``(language, origin, value)`` from the system's own settings.

    Each platform is asked where it keeps the user's choice first (see the
    module docstring); the locale Python reports is the last resort.
    """

    def desktop() -> tuple[str, str, str] | None:
        tags = [str(tag) for tag in system_languages or ()]
        lang = _first_supported(tags)
        return None if lang is None else (lang, ORIGIN_DESKTOP, ", ".join(tags))

    steps: tuple[_Step, ...]
    if sys.platform == "darwin":
        steps = (desktop, _macos_step, _posix_step)
    elif sys.platform == "win32":
        steps = (_windows_step, desktop, _posix_step)
    else:
        steps = (_posix_step, desktop)
    for step in steps:
        found = step()
        if found is not None:
            return found
    try:
        detected = py_locale.getlocale()[0]
    except (ValueError, TypeError):
        detected = None
    if detected:
        return normalize_lang(detected), ORIGIN_LOCALE, detected
    return DEFAULT_LANG, "", ""


def _first_supported(tags: Sequence[str]) -> str | None:
    """The first entry of a preferred-language list that ReverbScope has."""
    for tag in tags:
        lang = supported_language(tag)
        if lang is not None:
            return lang
    return None


def _macos_step() -> tuple[str, str, str] | None:
    languages = _macos_languages()
    lang = _first_supported(languages)
    return None if lang is None else (lang, ORIGIN_MACOS, ", ".join(languages))


def _windows_step() -> tuple[str, str, str] | None:
    """The Windows display language, when ReverbScope has it.

    A display language without a catalog (``zh_TW``, ``ja_JP``) leaves the
    choice to the next step, as on a Mac: Qt's UI languages in the GUI
    (Windows' own preferred-language list) and then ``LANG``.
    """
    windows = _windows_ui_language()
    lang = supported_language(windows)
    return None if lang is None or not windows else (lang, ORIGIN_WINDOWS, windows)


def _is_c_locale(value: str) -> bool:
    base = value.split(".", 1)[0].split("@", 1)[0]
    return base.upper() in {"", "C", "POSIX"}


def _posix_step() -> tuple[str, str, str] | None:
    """``LANGUAGE``, then ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``.

    gettext reads ``LANGUAGE`` only when the locale is set and is not C or
    POSIX, and takes its first entry that has a catalog. When none has one
    the locale variable decides. A variable set to C or POSIX is passed over,
    so ``LANG=C.UTF-8`` leaves the choice to the next step.
    """
    variables = [(name, os.environ.get(name, "")) for name in POSIX_VARIABLES]
    current = next((value for _name, value in variables if value), "")
    priority = os.environ.get("LANGUAGE", "")
    if current and not _is_c_locale(current) and priority:
        lang = _first_supported([tag for tag in priority.split(":") if tag])
        if lang is not None:
            return lang, "LANGUAGE", priority
    for name, value in variables:
        if value and not _is_c_locale(value):
            tag = value.split(".", 1)[0].split("@", 1)[0]
            return normalize_lang(tag), name, value
    return None


#: Where macOS keeps the user's preferred languages (``AppleLanguages``):
#: the user's global preferences first, then the computer's. Tests point it
#: at a fake file.
MACOS_PREFERENCES: tuple[str, ...] = (
    "~/Library/Preferences/.GlobalPreferences.plist",
    "/Library/Preferences/.GlobalPreferences.plist",
)


def _macos_languages(paths: Sequence[str | Path] | None = None) -> list[str]:
    """The Mac's preferred languages, in order (``["zh-Hans-CN", "en-CN"]``).

    Read from the global preferences with :mod:`plistlib`, which reads the
    binary and the XML form. Any failure (no such file, no ``HOME``, a damaged
    file, a list that is not a list) means "not available": ``[]``.
    """
    try:
        import plistlib  # needs xml.parsers.expat, which a trimmed bundle could lack
    except ImportError:
        return []
    for raw in MACOS_PREFERENCES if paths is None else paths:
        try:
            path = Path(raw).expanduser()
            with path.open("rb") as handle:
                data = plistlib.load(handle)
        except Exception:  # OSError, plistlib.InvalidFileException, RuntimeError (no HOME) …
            continue
        languages = data.get("AppleLanguages") if isinstance(data, dict) else None
        if isinstance(languages, list):
            found = [tag for tag in languages if isinstance(tag, str) and tag.strip()]
            if found:
                return found
    return []


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


_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _unquote(fragment: str) -> str:
    text = fragment.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    # One pass, so that "\\n" (a backslash, then n) is not read as a newline.
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m[1], m[0]), text)


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
