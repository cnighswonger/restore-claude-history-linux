"""Layer 1: Btrfs backend is_available() / discover() / parsing, mocked."""

from __future__ import annotations

import subprocess
from pathlib import Path

import backends.btrfs as btrfs_mod
from backends._mountinfo import Mount
from backends.btrfs import BtrfsBackend, _parse_subvol_line


def _cp(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["btrfs"], returncode=returncode,
                                       stdout=stdout, stderr="")


def _line(sid: str, path: str, otime: str = "2026-05-28 00:00:01") -> str:
    return f"ID {sid} gen 30 cgen 25 top level 5 otime {otime} path {path}"


# -------- _parse_subvol_line --------


def test_parse_normal_line():
    out = _parse_subvol_line(_line("256", "@/.snapshots/1/snapshot"))
    assert out == {"id": "256", "path": "@/.snapshots/1/snapshot",
                   "otime": "2026-05-28 00:00:01"}


def test_parse_missing_otime():
    out = _parse_subvol_line("ID 256 gen 30 cgen 25 top level 5 path @/snap")
    assert out["path"] == "@/snap"
    assert out["otime"] == ""


def test_parse_rejects_non_id_and_pathless():
    assert _parse_subvol_line("") is None
    assert _parse_subvol_line("garbage line here") is None
    assert _parse_subvol_line("ID 256 gen 30 top level 5") is None


# -------- _reachable_path --------


def _mnt(source="/dev/sda2", mountpoint="/", root="/@"):
    return Mount(fstype="btrfs", source=source, mountpoint=mountpoint, root=root)


def test_reachable_whole_fs_root():
    mounts = [_mnt(mountpoint="/mnt/top", root="/")]
    p, through = BtrfsBackend._reachable_path("@/.snapshots/1/snapshot", mounts)
    assert str(p) == "/mnt/top/@/.snapshots/1/snapshot"
    assert through == "/mnt/top"


def test_reachable_under_subvol_mount():
    mounts = [_mnt(mountpoint="/", root="/@")]
    p, through = BtrfsBackend._reachable_path("@/.snapshots/1/snapshot", mounts)
    assert str(p) == "/.snapshots/1/snapshot"
    assert through == "/"


def test_reachable_exact_subvol():
    mounts = [_mnt(mountpoint="/srv", root="/@data")]
    p, through = BtrfsBackend._reachable_path("@data", mounts)
    assert str(p) == "/srv"


def test_reachable_prefers_deepest_subvol_mount():
    # Both "/" (subvol @) and "/.snapshots" (subvol @/.snapshots) expose the
    # snapshot; the more specific mount must win.
    mounts = [
        _mnt(mountpoint="/", root="/@"),
        _mnt(mountpoint="/.snapshots", root="/@/.snapshots"),
    ]
    p, through = BtrfsBackend._reachable_path("@/.snapshots/1/snapshot", mounts)
    assert str(p) == "/.snapshots/1/snapshot"
    assert through == "/.snapshots"


def test_unreachable_when_not_under_any_mount():
    mounts = [_mnt(mountpoint="/", root="/@")]
    assert BtrfsBackend._reachable_path("@home/.snapshots/2/snapshot", mounts) is None


# -------- _is_shadowed --------


def test_is_shadowed_by_foreign_overmount():
    data_root = Path("/.snapshots/1/snapshot")
    foreign = [Mount(fstype="ext4", source="/dev/sdb1",
                     mountpoint="/.snapshots", root="/")]
    assert BtrfsBackend._is_shadowed(data_root, "/", {"/"}, foreign) is True


def test_not_shadowed_by_same_fs_overmount():
    data_root = Path("/.snapshots/1/snapshot")
    same = [_mnt(mountpoint="/.snapshots", root="/@/.snapshots")]
    assert BtrfsBackend._is_shadowed(data_root, "/", {"/", "/.snapshots"}, same) is False


def test_not_shadowed_when_no_deeper_mount():
    data_root = Path("/.snapshots/1/snapshot")
    assert BtrfsBackend._is_shadowed(data_root, "/", {"/"}, []) is False


# -------- is_available --------


def test_is_available_false_without_binary(monkeypatch):
    monkeypatch.setattr(btrfs_mod.shutil, "which", lambda _: None)
    assert BtrfsBackend().is_available() is False


def test_is_available_false_without_btrfs_mount(monkeypatch):
    monkeypatch.setattr(btrfs_mod.shutil, "which", lambda _: "/usr/bin/btrfs")
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [])
    assert BtrfsBackend().is_available() is False


def test_is_available_true(monkeypatch):
    monkeypatch.setattr(btrfs_mod.shutil, "which", lambda _: "/usr/bin/btrfs")
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [_mnt()])
    assert BtrfsBackend().is_available() is True


# -------- discover --------


def _stub_fs(monkeypatch, *, uuid=None, all_mounts=None):
    """Neutralize fs-UUID lookup + the mount-table read in discover tests."""
    monkeypatch.setattr(BtrfsBackend, "_fs_uuid", lambda self, mp: uuid)
    monkeypatch.setattr(btrfs_mod, "read_all_mounts", lambda: all_mounts or [])


def test_discover_resolves_paths_under_subvol_mount(monkeypatch):
    _stub_fs(monkeypatch)
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [_mnt()])
    out = (_line("256", "@/.snapshots/1/snapshot") + "\n"
           + _line("257", "@/.snapshots/2/snapshot") + "\n")
    monkeypatch.setattr(btrfs_mod, "_btrfs", lambda args: _cp(out))
    snaps = BtrfsBackend().discover()
    assert {str(s.data_root) for s in snaps} == {
        "/.snapshots/1/snapshot", "/.snapshots/2/snapshot"}
    assert all(s.needs_mount is False for s in snaps)
    one = next(s for s in snaps if s.name == "@/.snapshots/1/snapshot")
    assert one.backend_state["id"] == "256"


def test_discover_skips_unreachable_snapshots(monkeypatch):
    # Mounted subvol is @, but a snapshot lives under @home (different subvol).
    _stub_fs(monkeypatch)
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [_mnt()])
    out = (_line("256", "@/.snapshots/1/snapshot") + "\n"
           + _line("260", "@home/.snapshots/9/snapshot") + "\n")
    monkeypatch.setattr(btrfs_mod, "_btrfs", lambda args: _cp(out))
    snaps = BtrfsBackend().discover()
    assert [str(s.data_root) for s in snaps] == ["/.snapshots/1/snapshot"]


def test_discover_queries_each_fs_once_and_dedups(monkeypatch):
    # Two mounts of the SAME filesystem must not double-count snapshots.
    _stub_fs(monkeypatch)
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [
        _mnt(mountpoint="/", root="/@"),
        _mnt(mountpoint="/home", root="/@home"),
    ])
    calls = {"n": 0}

    def fake_btrfs(args):
        calls["n"] += 1
        return _cp(_line("256", "@/.snapshots/1/snapshot") + "\n")

    monkeypatch.setattr(btrfs_mod, "_btrfs", fake_btrfs)
    snaps = BtrfsBackend().discover()
    assert calls["n"] == 1  # queried once per filesystem
    assert [str(s.data_root) for s in snaps] == ["/.snapshots/1/snapshot"]


def test_discover_dedups_source_aliases_by_uuid(monkeypatch):
    # Round-1 HIGH fix: same fs mounted via two source aliases is ONE fs.
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [
        _mnt(source="/dev/sda2", mountpoint="/", root="/@"),
        _mnt(source="/dev/disk/by-uuid/XYZ", mountpoint="/mnt/top", root="/"),
    ])
    monkeypatch.setattr(BtrfsBackend, "_fs_uuid", lambda self, mp: "UUID-1")
    monkeypatch.setattr(btrfs_mod, "read_all_mounts", lambda: [])
    calls = {"n": 0}

    def fake_btrfs(args):
        calls["n"] += 1
        return _cp(_line("256", "@/.snapshots/1/snapshot") + "\n")

    monkeypatch.setattr(btrfs_mod, "_btrfs", fake_btrfs)
    snaps = BtrfsBackend().discover()
    assert calls["n"] == 1  # one fs -> one query, despite two source aliases
    assert len(snaps) == 1


def test_discover_skips_shadowed_snapshot(monkeypatch):
    # Round-1 MEDIUM fix: a foreign fs overmounted at /.snapshots masks the
    # snapshot bytes -> skip rather than emit a bogus data_root.
    _stub_fs(monkeypatch, all_mounts=[
        Mount(fstype="ext4", source="/dev/sdb1", mountpoint="/.snapshots", root="/"),
    ])
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts",
                        lambda self: [_mnt(mountpoint="/", root="/@")])
    monkeypatch.setattr(btrfs_mod, "_btrfs",
                        lambda args: _cp(_line("256", "@/.snapshots/1/snapshot") + "\n"))
    assert BtrfsBackend().discover() == []


def test_fs_uuid_parses_filesystem_show(monkeypatch):
    show = ("Label: 'none'  uuid: 1b3e7c44-aa00-4f00-9abc-deadbeef0001\n"
            "\tTotal devices 1 FS bytes used 1.00GiB\n"
            "\tdevid 1 size 10.00GiB used 2.00GiB path /dev/sda2\n")
    monkeypatch.setattr(btrfs_mod, "_btrfs", lambda args: _cp(show))
    assert BtrfsBackend()._fs_uuid("/") == "1b3e7c44-aa00-4f00-9abc-deadbeef0001"


def test_fs_uuid_none_on_failure(monkeypatch):
    monkeypatch.setattr(btrfs_mod, "_btrfs", lambda args: _cp(returncode=1))
    assert BtrfsBackend()._fs_uuid("/") is None


def test_discover_empty_when_btrfs_fails(monkeypatch):
    # Non-root / error: subvolume list returns non-zero -> no snapshots.
    _stub_fs(monkeypatch)
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [_mnt()])
    monkeypatch.setattr(btrfs_mod, "_btrfs", lambda args: _cp(returncode=1))
    assert BtrfsBackend().discover() == []


def test_discover_empty_without_mounts(monkeypatch):
    monkeypatch.setattr(BtrfsBackend, "_btrfs_mounts", lambda self: [])
    assert BtrfsBackend().discover() == []
