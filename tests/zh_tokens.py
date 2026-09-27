"""English words a Simplified Chinese interface may show.

Product, standard and DAW names, units and file formats stay in Latin
letters in the Chinese interface; everything else a user reads must be
Chinese. Used by the GUI and CLI zh_CN gates. Commands (``roomscope
analyze``), file names (``result.json``) and flags (``--probe``) are removed
before a text is checked.
"""

from __future__ import annotations

import re

ALLOWED = frozenset(
    {
        # RoomScope, metrics, units, standards
        "RoomScope",
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
        "Schema",
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
        "Core",
        "Audio",
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
        # DAWs and their feature names (menus stay in the vendors' language)
        "DAW",
        "Pro",
        "Tools",
        "Logic",
        "GarageBand",
        "Cubase",
        "Nuendo",
        "Studio",
        "One",
        "Fender",
        "Ableton",
        "Live",
        "REAPER",
        "Bitwig",
        "Digital",
        "Performer",
        "Audacity",
        "Ardour",
        "Cakewalk",
        "Warp",
        "Flex",
        "Time",
        "Follow",
        "Tempo",
        "Elastic",
        # GitHub, where test reports go; language names
        "GitHub",
        "Issue",
        "English",
        "https",
    }
)

_COMMAND = re.compile(r"roomscope(?:\s+[a-z][a-z-]*)?(?:\s+--?[\w-]+)*")
_WORD = re.compile(r"(?<![\w./\\%{\[-])[A-Za-z][A-Za-z']{2,}(?![\w./\\}\]-])")


def english_words(text: str, *, data: tuple[str, ...] = ()) -> list[str]:
    """Latin-letter words in ``text`` that a Chinese interface should not show.

    ``data`` are values from the user's files or devices (room names, device
    names) that are shown as they are.
    """
    for value in data:
        if value:
            text = text.replace(value, " ")
    # The English term glossed once after the Chinese one: 回送（loopback）.
    text = text.replace("（loopback）", "")
    text = _COMMAND.sub(" ", text)
    return [word for word in _WORD.findall(text) if word not in ALLOWED]
