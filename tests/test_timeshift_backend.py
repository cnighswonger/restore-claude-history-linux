"""Layer 1: Timeshift backend is_available() + discover() using tempdir trees."""

from __future__ import annotations

import json

from backends.timeshift import TimeshiftBackend


def _config(tmp_path, btrfs_mode="false"):
    cfg = tmp_path / "timeshift.json"
    cfg.write_text(json.dumps({"btrfs_mode": btrfs_mode, "snapshot_count": "3"}))
    return cfg


def _backend(tmp_path, base, btrfs_mode="false"):
    return TimeshiftBackend(config_path=_config(tmp_path, btrfs_mode),
                            snapshot_bases=(base,))


# -------- is_available --------


def test_is_available_true_when_config_parses(tmp_path):
    b = TimeshiftBackend(config_path=_config(tmp_path), snapshot_bases=())
    assert b.is_available() is True


def test_is_available_false_when_config_missing(tmp_path):
    b = TimeshiftBackend(config_path=tmp_path / "nope.json", snapshot_bases=())
    assert b.is_available() is False


def test_is_available_false_on_invalid_json(tmp_path):
    cfg = tmp_path / "timeshift.json"
    cfg.write_text("{not valid json")
    b = TimeshiftBackend(config_path=cfg, snapshot_bases=())
    assert b.is_available() is False


# -------- discover --------


def test_discover_rsync_snapshots(tmp_path):
    base = tmp_path / "snapshots"
    for ts in ("2026-05-28_00-00-01", "2026-05-28_12-00-01"):
        (base / ts / "localhost").mkdir(parents=True)
    snaps = _backend(tmp_path, base).discover()
    assert {str(s.data_root) for s in snaps} == {
        str(base / "2026-05-28_00-00-01" / "localhost"),
        str(base / "2026-05-28_12-00-01" / "localhost"),
    }
    assert all(s.needs_mount is False for s in snaps)
    assert {s.name for s in snaps} == {"2026-05-28_00-00-01", "2026-05-28_12-00-01"}


def test_discover_btrfs_prefers_home_subvol(tmp_path):
    base = tmp_path / "snapshots"
    ts = base / "2026-05-28_00-00-01"
    (ts / "@home").mkdir(parents=True)
    (ts / "@").mkdir(parents=True)
    snaps = _backend(tmp_path, base, btrfs_mode="true").discover()
    assert [str(s.data_root) for s in snaps] == [str(ts / "@home")]


def test_discover_btrfs_single_root_subvol(tmp_path):
    base = tmp_path / "snapshots"
    ts = base / "2026-05-28_00-00-01"
    (ts / "@").mkdir(parents=True)
    snaps = _backend(tmp_path, base, btrfs_mode="true").discover()
    assert [str(s.data_root) for s in snaps] == [str(ts / "@")]


def test_discover_fallback_to_timestamp_dir(tmp_path):
    base = tmp_path / "snapshots"
    ts = base / "2026-05-28_00-00-01"
    ts.mkdir(parents=True)  # no localhost/@home/@ subdir
    snaps = _backend(tmp_path, base).discover()
    assert [str(s.data_root) for s in snaps] == [str(ts)]


def test_discover_ignores_non_dir_entries(tmp_path):
    base = tmp_path / "snapshots"
    (base / "2026-05-28_00-00-01" / "localhost").mkdir(parents=True)
    (base / "info.json").write_text("{}")  # stray file in base
    snaps = _backend(tmp_path, base).discover()
    assert len(snaps) == 1


def test_discover_dedups_by_realpath(tmp_path):
    # Two bases, one a symlink to the other -> same snapshot, one entry.
    real = tmp_path / "snapshots"
    (real / "2026-05-28_00-00-01" / "localhost").mkdir(parents=True)
    link = tmp_path / "snapshots-link"
    link.symlink_to(real)
    b = TimeshiftBackend(config_path=_config(tmp_path), snapshot_bases=(real, link))
    assert len(b.discover()) == 1


def test_discover_empty_without_config(tmp_path):
    base = tmp_path / "snapshots"
    (base / "2026-05-28_00-00-01" / "localhost").mkdir(parents=True)
    b = TimeshiftBackend(config_path=tmp_path / "nope.json", snapshot_bases=(base,))
    assert b.discover() == []


def test_discover_empty_when_base_missing(tmp_path):
    b = _backend(tmp_path, tmp_path / "does-not-exist")
    assert b.discover() == []
