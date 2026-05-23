#!/usr/bin/env python3
"""
verify_restore.py — end-to-end test for restore_claude_history.py

Builds a sandbox from your real ~/.claude/projects/<project>, deletes a few
files from the sandbox, runs the main script with --dest, then checks that
the deleted files came back with correct sizes, correct historical mtimes,
and no inherited TM ACL. Cleans up after itself.

Usage:
    python3 tests/verify_restore.py --project=-Users-you-projects-foo
    python3 tests/verify_restore.py --project=-Users-you-projects-foo --keep

Requires: a Time Machine drive plugged in with snapshots containing the
chosen project. Same prereqs as the main script (Full Disk Access etc.).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_SCRIPT = REPO_ROOT / "restore_claude_history.py"
CLAUDE_DIR = Path.home() / ".claude" / "projects"
NUM_FILES_TO_TEST = 5


@dataclass
class FileFingerprint:
    path: Path
    size: int
    mtime: float


def fingerprint(path: Path) -> FileFingerprint:
    st = path.stat()
    return FileFingerprint(path=path, size=st.st_size, mtime=st.st_mtime)


def has_acl(path: Path) -> bool:
    """`ls -le` shows a '+' after the permission bits when ACLs are present."""
    out = subprocess.run(["ls", "-le", str(path)], capture_output=True, text=True).stdout
    # Lines look like:  -rw-------+ 1 user staff ...
    # vs (no ACL):      -rw-------  1 user staff ...
    # vs (xattrs only): -rw-------@ 1 user staff ...
    m = re.match(r"^\S+", out)
    return bool(m and "+" in m.group(0))


def latest_backup_time() -> float | None:
    """Return the unix mtime of the most recent TM backup, or None if unknown.

    `tmutil latestbackup` returns a path with the timestamp embedded:
        /Volumes/.timemachine/<UUID>/2026-04-24-205237.backup/2026-04-24-205237.backup
    """
    r = subprocess.run(["tmutil", "latestbackup"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2}-\d{6})\.backup", r.stdout)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1), "%Y-%m-%d-%H%M%S").timestamp()


def pick_test_files(project_dir: Path) -> list[FileFingerprint]:
    """Pick a spread of JSONLs that exist in at least one TM snapshot.

    Filters out files newer than the latest TM backup, since those can't
    possibly be restored (they don't exist in any snapshot).
    """
    cutoff = latest_backup_time()
    candidates = list(project_dir.glob("*.jsonl"))
    if cutoff is not None:
        before = len(candidates)
        candidates = [p for p in candidates if p.stat().st_mtime <= cutoff]
        skipped = before - len(candidates)
        if skipped:
            print(f"[setup]  skipping {skipped} file(s) newer than latest TM backup")
    candidates.sort(key=lambda p: p.stat().st_size)
    if len(candidates) < NUM_FILES_TO_TEST:
        die(f"Only {len(candidates)} eligible JSONLs; need at least {NUM_FILES_TO_TEST}.")
    # Pick evenly across the size distribution.
    step = max(1, len(candidates) // NUM_FILES_TO_TEST)
    picks = candidates[::step][:NUM_FILES_TO_TEST]
    return [fingerprint(p) for p in picks]


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True,
                        help="encoded project dir under ~/.claude/projects "
                             "(e.g. -Users-you-projects-foo)")
    parser.add_argument("--keep", action="store_true",
                        help="leave the sandbox in /tmp after the run (for inspection)")
    # Same dash-eating workaround as the main script.
    argv = sys.argv[1:]
    rewritten: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--project" and i + 1 < len(argv) and argv[i + 1].startswith("-"):
            rewritten.append(f"--project={argv[i + 1]}")
            i += 2
        else:
            rewritten.append(argv[i])
            i += 1
    args = parser.parse_args(rewritten)

    real_project = CLAUDE_DIR / args.project
    if not real_project.is_dir():
        die(f"No such project on disk: {real_project}")

    # Set up sandbox.
    sandbox_root = Path(tempfile.mkdtemp(prefix="claude-restore-verify-"))
    sandbox_project = sandbox_root / args.project
    print(f"[setup]  sandbox: {sandbox_project}")
    shutil.copytree(real_project, sandbox_project)

    # Pick + delete test files. Capture fingerprints from the REAL files
    # (sandbox copies have today's mtime because cp doesn't preserve it).
    real_picks = pick_test_files(real_project)
    print(f"[setup]  picked {len(real_picks)} files to delete + restore:")
    for fp in real_picks:
        print(f"           {fp.size:>10} bytes  mtime={fp.mtime}  {fp.path.name}")
        (sandbox_project / fp.path.name).unlink()

    # Run main script against sandbox.
    print(f"[run]    {MAIN_SCRIPT} --dest {sandbox_root} --project={args.project}")
    result = subprocess.run(
        [str(MAIN_SCRIPT), "--dest", str(sandbox_root),
         f"--project={args.project}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        die(f"restore script exited {result.returncode}")
    # Surface the last line of output (the summary).
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    print(f"[run]    {summary}")

    # Verify.
    failures: list[str] = []
    for original in real_picks:
        restored = sandbox_project / original.path.name
        if not restored.exists():
            failures.append(f"missing: {restored}")
            continue
        rst = restored.stat()
        if rst.st_size != original.size:
            failures.append(
                f"size mismatch on {restored.name}: "
                f"got {rst.st_size}, want {original.size}"
            )
        if abs(rst.st_mtime - original.mtime) > 1.0:
            failures.append(
                f"mtime drift on {restored.name}: "
                f"got {rst.st_mtime}, want {original.mtime} "
                f"(diff {rst.st_mtime - original.mtime:.1f}s)"
            )
        if has_acl(restored):
            failures.append(f"ACL still present on {restored.name}")

    # Clean up unless --keep.
    if args.keep:
        print(f"[keep]   sandbox left at {sandbox_root}")
    else:
        shutil.rmtree(sandbox_root, ignore_errors=True)
        print(f"[clean]  removed {sandbox_root}")

    if failures:
        print()
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print()
    print(f"PASS: {len(real_picks)} files restored with correct size, mtime, no ACL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
