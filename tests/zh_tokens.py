"""English words a Simplified Chinese interface may show.

Product, standard and DAW names, units and file formats stay in Latin
letters in the Chinese interface; everything else a user reads must be
Chinese. Used by the GUI and CLI zh_CN gates. Commands (``reverbscope
analyze``), file names (``result.json``) and flags (``--probe``) are removed
before a text is checked.
"""

from __future__ import annotations

import re

ALLOWED = frozenset(
    {
        # ReverbScope, metrics, units, standards
        "ReverbScope",
        "RT60",
        "EDT",
        "T20",
        "T30",
        "RMS",
        "SPL",
        "ISO",
        "dBFS",
        "kHz",
        "Lundeby",
        "Schroeder",
        "Hann",
        "ESS",
        "PSD",
        "IR",
        # file formats and data
        "WAV",
        "AIFF",
        "CAF",
        "FLAC",
        "BWF",
        "RF64",
        "W64",
        "JSON",
        "CSV",
        "ZIP",
        "UTF",
        # audio systems and platforms
        "API",
        "PortAudio",
        "WASAPI",
        "ASIO",
        "MME",
        "DirectSound",
        "WDM",
        "ALSA",
        "JACK",
        "PipeWire",
        "PulseAudio",
        "macOS",
        "Windows",
        "Linux",
        "USB",
        "Thunderbolt",
        "fake",
        "portaudio",
        # the value of --format ("reverbscope --format json")
        "json",
        "pip",
        # DAWs and their feature names (menus stay in the vendors' language)
        "DAW",
        "Logic",
        "GarageBand",
        "Cubase",
        "Nuendo",
        "Ableton",
        "REAPER",
        "Bitwig",
        "Audacity",
        "Ardour",
        "Cakewalk",
        "Warp",
        "Flex",
        # GitHub, where test reports go; language names
        "GitHub",
        # License and library names kept in Latin in the About box.
        "Apache",
        "GNU",
        "LGPL",
        "NumPy",
        "SciPy",
        "matplotlib",
        "soundfile",
        "libsndfile",
        "sounddevice",
    }
)

#: Names of more than one word, removed as a whole so that their single words
#: ("One", "Live", "Time", "Core") are not allowed on their own.
PHRASES = (
    "Fender Studio Pro",
    "Pro Tools",
    "Logic Pro",
    "Studio One",
    "FL Studio",
    "Bitwig Studio",
    "Ableton Live",
    "Digital Performer",
    "Core Audio",
    "Flex Time",
    "Follow Tempo",
    "Elastic Audio",
    "JSON Schema",
    "GitHub Issue",
)
_URL = re.compile(r"https?://\S+")
# A command and, for "project" and "session", its action ("reverbscope project init").
_COMMAND = re.compile(r"reverbscope(?:[ \t]+[a-z][a-z-]*){0,2}(?:[ \t]+--?[\w-]+)*")
_WORD = re.compile(r"(?<![\w./\\%{\[-])[A-Za-z][A-Za-z']{2,}(?![\w./\\}\]-])")


def english_words(
    text: str, *, data: tuple[str, ...] = (), values: tuple[str, ...] = ()
) -> list[str]:
    """Latin-letter words in ``text`` that a Chinese interface should not show.

    ``data`` are values from the user's files or devices (room names, device
    names) that are shown as they are. ``values`` are words a user types as
    they are (``reverbscope config theme dark``), removed only as whole words.
    """
    for value in data:
        if value:
            text = text.replace(value, " ")
    if values:
        typed = "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
        text = re.sub(rf"(?<![\w-])(?:{typed})(?![\w-])", " ", text)
    text = _URL.sub(" ", text)
    for phrase in PHRASES:
        text = text.replace(phrase, " ")
    # The English term glossed once after the Chinese one: 回采（loopback）.
    text = text.replace("（loopback）", "")
    text = _COMMAND.sub(" ", text)
    return [word for word in _WORD.findall(text) if word not in ALLOWED]


#: Chinese, and the full-width marks around it.
CJK = re.compile(r"[一-鿿　-〿＀-￯]")
#: A ``--flag`` or ``-h`` the user types as it is.
_FLAG = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")
#: What the Chinese interface writes full-width: an ASCII bracket, a comma or
#: semicolon followed by a space, a colon beside Chinese, a quote beside Chinese.
_ASCII_PUNCTUATION = re.compile(
    r"[()]"
    r"|[,;] "
    r"|(?<=[一-鿿]):"
    r"|:(?= ?[一-鿿])"
    r"|['\"](?=[一-鿿])"
    r"|(?<=[一-鿿])['\"]"
)


def ascii_punctuation(text: str, *, allowed: tuple[str, ...] = ()) -> list[str]:
    """Lines of ``text`` that hold Chinese and ASCII punctuation: ``50 Hz (+57 dB),
    100 Hz`` where the interface writes ``50 Hz（+57 dB）、100 Hz``.

    URLs, commands and flags are removed first (``-h, --help`` is argparse's);
    ``allowed`` are literal pieces to remove as well (an example the user is
    told to type, ``1,2``).
    """
    found = []
    for line in text.splitlines():
        if not CJK.search(line):
            continue
        shown = _URL.sub(" ", line)
        for piece in allowed:
            shown = shown.replace(piece, " ")
        shown = _COMMAND.sub(" ", shown)
        shown = _FLAG.sub(" ", shown)
        if _ASCII_PUNCTUATION.search(shown):
            found.append(line.strip())
    return found
