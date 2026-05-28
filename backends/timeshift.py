"""Timeshift snapshot backend.

Timeshift is Ubuntu's default backup tool. It runs in one of two modes,
recorded in ``/etc/timeshift/timeshift.json``:

- **RSYNC mode** — snapshots are plain directory trees at
  ``/timeshift/snapshots/<timestamp>/localhost/`` (a full root-filesystem copy).
- **BTRFS mode** — snapshots are Btrfs subvolumes (``@``, ``@home``) under a
  ``timeshift-btrfs/snapshots/<timestamp>/`` directory on the backup device,
  reachable at ``/timeshift-btrfs/snapshots`` or, while Timeshift has the
  device mounted, ``/run/timeshift/<pid>/backup/timeshift-btrfs/snapshots``.

This backend scans those locations and reports each snapshot's data root.
needs_mount=False: it reads snapshots that are already on disk and never mounts
the backup device itself (if BTRFS-mode snapshots aren't currently exposed,
they're simply not found — v1 does not mount on the user's behalf).

Per the v1 directive, Timeshift OWNS Timeshift-on-Btrfs snapshots: the
orchestrator prunes a Btrfs-backend duplicate of the same canonical path in
``auto`` mode (the overlap pass, now active because this backend is
registered). The backend itself does no cross-backend handling.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backends.base import DiscoveredSnapshot, SnapshotBackend

_CONFIG_PATH = Path("/etc/timeshift/timeshift.json")
# Persistent locations Timeshift exposes snapshots at (RSYNC + BTRFS modes).
_SNAPSHOT_BASES = (
    Path("/timeshift/snapshots"),
    Path("/timeshift-btrfs/snapshots"),
)
# Per-snapshot subdirectories that hold the filesystem root, in probe order.
_DATA_SUBDIRS = ("localhost", "@home", "@")


class TimeshiftBackend(SnapshotBackend):
    name = "timeshift"

    def __init__(
        self,
        config_path: Path = _CONFIG_PATH,
        snapshot_bases: tuple[Path, ...] = _SNAPSHOT_BASES,
    ) -> None:
        self.config_path = config_path
        self.snapshot_bases = snapshot_bases

    def _load_config(self) -> dict | None:
        try:
            return json.loads(self.config_path.read_text())
        except (OSError, ValueError):
            return None

    def is_available(self) -> bool:
        """True when Timeshift is configured (its config file parses).

        Config presence is the "Timeshift is set up on this host" signal; we
        do not check whether snapshots exist.
        """
        return self._load_config() is not None

    def _snapshot_base_dirs(self) -> list[Path]:
        bases = list(self.snapshot_bases)
        # BTRFS-mode snapshots while Timeshift has the device mounted.
        run = Path("/run/timeshift")
        if run.is_dir():
            bases.extend(sorted(run.glob("*/backup/timeshift-btrfs/snapshots")))
        return [b for b in bases if b.is_dir()]

    @staticmethod
    def _snapshot_data_root(ts_dir: Path) -> Path:
        """The filesystem root inside a snapshot timestamp dir.

        RSYNC -> <ts>/localhost; BTRFS -> <ts>/@home (home subvol) or <ts>/@
        (single root subvol). Falls back to the timestamp dir itself.
        """
        for sub in _DATA_SUBDIRS:
            if (ts_dir / sub).is_dir():
                return ts_dir / sub
        return ts_dir

    def discover(self) -> list[DiscoveredSnapshot]:
        if self._load_config() is None:
            return []
        snaps: list[DiscoveredSnapshot] = []
        seen: set[str] = set()
        for base in self._snapshot_base_dirs():
            for ts_dir in sorted(base.iterdir()):
                if not ts_dir.is_dir():
                    continue
                data_root = self._snapshot_data_root(ts_dir)
                key = os.path.realpath(str(data_root))
                if key in seen:
                    continue
                seen.add(key)
                snaps.append(DiscoveredSnapshot(
                    name=ts_dir.name,
                    data_root=data_root,
                    needs_mount=False,
                    backend_state={"timestamp": ts_dir.name, "base": str(base)},
                ))
        return snaps
