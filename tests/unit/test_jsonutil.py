from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from reverbscope.io import jsonutil
from reverbscope.io.jsonutil import write_text_atomic


def test_overlapping_atomic_writes_do_not_share_a_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every writer used ``.recent_sessions.json.tmp``: a second ReverbScope
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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_keep_beside_links_or_copies_the_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hard link where it can; a copy on a file system without links and
    for a read-only file, whose links would share its read-only flag."""
    import os

    from reverbscope.io.jsonutil import keep_beside

    member = tmp_path / "result.json"
    member.write_text("take A", encoding="utf-8")
    linked = keep_beside(member, ".previous.json")
    assert linked.read_text(encoding="utf-8") == "take A" and member.stat().st_nlink == 2
    linked.unlink()
    member.chmod(0o444)
    copied = keep_beside(member, ".previous.json")
    assert member.stat().st_nlink == 1 and copied.stat().st_mode & 0o777 == 0o444
    member.chmod(0o644)

    def no_links(*_args: object, **_kwargs: object) -> None:
        raise OSError(1, "Operation not permitted")  # exFAT

    monkeypatch.setattr(os, "link", no_links)
    copied = keep_beside(member, ".previous.json")
    assert copied.read_text(encoding="utf-8") == "take A" and member.stat().st_nlink == 1


@pytest.mark.skipif(sys.platform == "win32", reason="emulates Windows on POSIX permissions")
def test_a_refused_atomic_write_leaves_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows refuses to replace a read-only file. The temporary had taken
    its read-only mode, so deleting it raised too: that error replaced the
    real one and the '.settings.<pid>-<hex>.json.tmp' file stayed behind."""
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    target.chmod(0o444)
    real_replace, real_unlink = os.replace, Path.unlink

    def read_only(path: object) -> bool:
        return os.path.exists(path) and not os.stat(path).st_mode & stat.S_IWUSR  # type: ignore[arg-type]

    def replace(src: str, dst: str) -> None:
        if read_only(dst):
            raise PermissionError(13, "Access is denied", str(dst))
        real_replace(src, dst)

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if read_only(self):
            raise PermissionError(13, "Access is denied", str(self))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError) as raised:
        write_text_atomic(target, '{"language": "zh_CN"}')
    assert raised.value.filename == str(target)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]


def test_a_json_file_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    """Notepad's "UTF-8 with BOM" and Windows PowerShell 5's -Encoding UTF8
    write one: a hand-edited session.json was refused with the parser's
    English "Unexpected UTF-8 BOM", and settings.json was silently ignored."""
    edited = tmp_path / "session.json"
    edited.write_bytes(b"\xef\xbb\xbf" + '{"room_name": "录音棚"}'.encode())
    assert jsonutil.read_json_object(edited) == {"room_name": "录音棚"}
