"""The command line the menu prints is one command, with the words it runs.

"The same from the command line" is typed or pasted into a shell next time:
every argument outside letters, digits and ``. / - _ : , = @ % +`` is quoted, so
that a name with a space, a bracket, a dollar or an invisible character is
still one word. Checked through ``shlex`` and through bash.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from reverbscope.cli.console import shell_command
from tests.menus import drive

POSIX = os.name != "nt"


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


NAMES = [
    "录音(1).wav",
    "a&b.wav",
    "a;b.wav",
    "#hash.wav",
    "$HOME.wav",
    "a*b.wav",
    "a|b.wav",
    "a'b.wav",
    'a"b.wav',
    "a\\b.wav",
    "a b.wav",
    "~x.wav",
    "=x.wav",
    "a^b.wav",
    "a<b>.wav",
    "a!b.wav",
    "a`b.wav",
    "{a,b}.wav",
    "a\tb.wav",
    "a\x1bb.wav",
    "a\u200bb.wav",
    "a\u202eb.wav",
    "-x.wav",
    "50%.wav",
    "a@b+c=d,e:f.wav",
    "我的录音.wav",
]


@pytest.mark.skipif(not POSIX, reason="a POSIX shell reads the command")
@pytest.mark.parametrize("name", NAMES)
def test_the_command_to_copy_is_the_same_words_in_a_shell(name: str, tmp_path: Path) -> None:
    """Every argument outside letters, digits and ``. / - _ : , = @ % +`` is
    quoted, so the printed line is one command with the words the menu runs."""
    recording = tmp_path / "rec.wav"
    recording.write_bytes(b"RIFF")
    (tmp_path / "sweep.wav").write_bytes(b"RIFF")
    # Typed the way a terminal drops it: quoted for a shell, which a backslash needs.
    visit = drive(["3", str(recording), "", shlex.quote(name), "q"])
    argv = ["analyze", "--recording", str(recording), "--sweep", str(tmp_path / "sweep.wav")]
    argv += ["--out", name]
    assert visit.runs == [argv]
    line = next(
        raw.strip()
        for raw in visit.lines
        if raw.startswith("    reverbscope ") and "analyze" in raw
    )
    assert line == shell_command(["reverbscope", *argv])
    assert shlex.split(line) == ["reverbscope", *argv]
    shell = shutil.which("bash") or shutil.which("sh")
    assert shell is not None
    echoed = subprocess.run(
        [shell, "-c", line.replace("reverbscope", "printf '<%s>' ", 1)],
        capture_output=True,
        check=True,
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": "/nonexistent"},
    )
    assert echoed.stdout.decode("utf-8") == "".join(f"<{word}>" for word in argv)


SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789./-_:,=@%+")


@pytest.mark.skipif(not POSIX, reason="a POSIX shell reads the command")
@pytest.mark.parametrize(
    "char",
    [chr(code) for code in range(1, 128) if chr(code) not in SAFE] + ["\u00a0", "\u200b", "\u202e"],
    ids=lambda char: f"U+{ord(char):04X}",
)
def test_every_character_outside_the_safe_ones_gets_the_argument_quoted(char: str) -> None:
    for word in (f"a{char}b", f"{char}ab", f"ab{char}", char):
        line = shell_command(["x", word])
        assert line != f"x {word}", repr(word)
        assert shlex.split(line) == ["x", word]


def test_a_plain_command_is_not_quoted() -> None:
    line = shell_command(["reverbscope", "analyze", "--out", "我的/录音_1.wav", "a@b+c=d,e:f%"])
    assert line == "reverbscope analyze --out 我的/录音_1.wav a@b+c=d,e:f%"
