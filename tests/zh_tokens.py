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
        # Welch's method (the noise view's power spectral density)
        "Welch",
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
        # room scans the desktop room view imports
        "PLY",
        "OBJ",
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
        "pyqtgraph",
        "MIT",
        # Key names in shortcut hints ("Ctrl+Return", "Esc"), as on the keyboard.
        "Ctrl",
        "Return",
        "Esc",
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
    # pyqtgraph's copyright holders, named in the About box as its license asks.
    "University of North Carolina at Chapel Hill",
    "Luke Campagnola",
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
    # The English term glossed once after the Chinese one: 回送（loopback）.
    text = text.replace("（loopback）", "")
    text = _COMMAND.sub(" ", text)
    return [word for word in _WORD.findall(text) if word not in ALLOWED]
