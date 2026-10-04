from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from roomscope.io import jsonutil
from roomscope.io.jsonutil import write_text_atomic


def test_overlapping_atomic_writes_do_not_share_a_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every writer used ``.recent_sessions.json.tmp``: a second RoomScope
    (the GUI and a CLI run) wrote into the first one's temporary and renamed
    it away, so the first failed with FileNotFoundError."""
    target = tmp_path / "recent_sessions.json"
    real_fsync = os.fsync
    nested: list[int] = []

    def fsync_then_another_writer(descriptor: int) -> None:
        real_fsync(descriptor)
        if not nested:
            nested.append(descriptor)
            write_text_atomic(target, json.dumps({"sessions": ["other"]}))

    monkeypatch.setattr(jsonutil.os, "fsync", fsync_then_another_writer)
    write_text_atomic(target, json.dumps({"sessions": ["mine"]}))
    assert nested
    assert json.loads(target.read_text(encoding="utf-8")) == {"sessions": ["mine"]}
    assert [path.name for path in tmp_path.iterdir()] == [target.name]


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need a privilege")
def test_atomic_write_does_not_follow_a_planted_temporary_link(tmp_path: Path) -> None:
    """The temporary name was fixed and opened without O_EXCL: a link under
    that name in a folder from someone else redirected the write."""
    folder = tmp_path / "received"
    folder.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    (folder / ".session.json.tmp").symlink_to(victim)
    write_text_atomic(folder / "session.json", "{}")
    assert victim.read_text(encoding="utf-8") == "keep me"
    assert not (folder / "session.json").is_symlink()
    assert (folder / "session.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions and links")
def test_atomic_write_keeps_the_mode_and_follows_links_only_when_asked(tmp_path: Path) -> None:
    private = tmp_path / "project.json"
    private.write_text("{}", encoding="utf-8")
    private.chmod(0o600)
    write_text_atomic(private, '{"name": "Booth"}')
    assert stat.S_IMODE(private.stat().st_mode) == 0o600

    real = tmp_path / "dotfiles" / "recent_sessions.json"
    real.parent.mkdir()
    real.write_text("{}", encoding="utf-8")
    followed = tmp_path / "followed.json"
    followed.symlink_to(real)
    write_text_atomic(followed, '{"sessions": []}', follow_symlinks=True)
    assert followed.is_symlink()
    assert real.read_text(encoding="utf-8") == '{"sessions": []}'

    # A session or project file is replaced, never written through a link.
    replaced = tmp_path / "session.json"
    replaced.symlink_to(real)
    write_text_atomic(replaced, '{"room_name": "X"}')
    assert not replaced.is_symlink()
    assert real.read_text(encoding="utf-8") == '{"sessions": []}'
