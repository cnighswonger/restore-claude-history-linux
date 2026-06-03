# restore-claude-history

Recover deleted Claude Code chat transcripts from macOS Time Machine snapshots.

## Background

Claude Code stores chat transcripts as JSONL files under `~/.claude/projects/<encoded-cwd>/`. A cleanup job prunes them after `cleanupPeriodDays` (default: **30 days**, undocumented, no warning). If you haven't changed that setting, you've probably already lost months of conversations.

If you have a macOS Time Machine drive — or if you have local APFS snapshots on your internal disk (typically present even when the drive is unplugged, as long as you've run Time Machine recently) — this script ([`restore_claude_history.py`](restore_claude_history.py)) can get them back.

## Prevention first

Before anything else, add this to `~/.claude/settings.json`:

```json
"cleanupPeriodDays": 36500
```

That's ~100 years. There's no documented upper bound; the schema just wants a positive integer. Do this on every machine you use Claude Code on.

**Set this *and* keep backups — not one or the other.** The setting defangs the documented cleanup, but multiple user reports (e.g. [#41458](https://github.com/anthropics/claude-code/issues/41458)) describe chats vanishing *despite* the flag being set, most often around app updates. That's why this script exists alongside the prevention step, not instead of it.

## Recovery

This script: [`restore_claude_history.py`](restore_claude_history.py)

### Requirements

- macOS with **at least one** of:
  - An APFS Time Machine drive that has snapshots, *or*
  - Local APFS snapshots on your internal disk (run `tmutil listlocalsnapshots /System/Volumes/Data` to check). These are typically present whenever Time Machine has run recently, even if the drive is currently unplugged.
- **Full Disk Access** for whatever app runs the script (Terminal, iTerm, VS Code)
  - System Settings → Privacy & Security → Full Disk Access → +
- Python 3.7+ (the system `python3` from Apple's Command Line Tools is fine)

### Quickstart

```bash
git clone https://github.com/garrettmoss/restore-claude-history
cd restore-claude-history

# See what would be restored, no changes made. Uses whichever sources
# are available — TM drive (if plugged in) and local snapshots:
python3 restore_claude_history.py --dry-run --verbose

# Actually restore:
python3 restore_claude_history.py
```

> If your TM drive is unplugged, the script will fall through to local snapshots automatically. Local snapshots only cover ~24h to whenever you last ran a Time Machine backup, so they're a recent-deletion safety net, not a deep archive — plug the drive in if you need older chats.

### Flags

| Flag | What it does |
|---|---|
| `--dry-run` | Show what would be restored, copy nothing. Always run this first. |
| `--source local\|tm\|both` | Which snapshot pool to search. Default `both` (uses whichever is available). `local` skips the TM drive entirely; `tm` requires it. |
| `--project NAME` | Limit to one encoded project dir (e.g. `--project=-Users-you-projects-foo`). Note the `=` — encoded names start with `-`. |
| `--include-memory` | Also restore `<project>/memory/` subdirs. |
| `--verbose` | Log every file decision, not just the summary. |
| `--dest DIR` | Restore into `DIR` instead of `~/.claude/projects` (for testing). |
| `--list-only` | Don't restore anything; just print one tab-separated row per `(project, filename)` pair found in available snapshots (`kind`, `snapshot`, `project`, `filename`, `size`, `mtime`). Useful for previewing what's recoverable. Status text routes to stderr in this mode so stdout stays parse-clean. |

### What it does

1. Finds available snapshot sources per `--source`: your TM drive (if plugged in), the internal Data volume's local APFS snapshots, or both.
2. Walks snapshots **newest-first**, mounting one at a time (read-only), indexing, restoring, and unmounting before moving to the next. Reuses any mounts macOS already auto-mounted instead of remounting.
3. For each `(project, filename)`, takes the **first** version seen — JSONLs are append-only, so the newest snapshot containing a file holds the largest copy. Once restored from one snapshot, older snapshots skip that file.
4. Copies it back, **preserving the original mtime** and stripping the inherited Time Machine ACL so the restored files remain writable.
5. Skips files where your on-disk version is already the same size or larger — so active or in-progress chats are never overwritten with an older snapshot.
6. Cleans up the snapshots it mounted (leaves any pre-existing system mounts alone).

### Verifying it works

There's an end-to-end test that builds a sandbox from your real chats, picks files known to be present in your snapshots, deletes them, restores them, and checks size/mtime/ACL match the snapshot:

```bash
python3 tests/verify_restore.py --project=-Users-you-projects-foo
# Or pin a specific source (handy when validating without the TM drive plugged in):
python3 tests/verify_restore.py --project=-Users-you-projects-foo --source=local
```

## Background reading

See [NOTES.md](NOTES.md) for the full story: how the bug works, what Time Machine snapshots actually look like, what we tried that didn't work, and the verified working commands from the original recovery session.

### See also

This tool covers exactly one slice of the disappearing-Claude-chats problem: macOS, Time Machine, JSONLs deleted from disk. If that's not your situation, one of these may help. Grouped by platform.

**macOS:**
- **[DeveloperAlly/claude-code-survival-toolkit](https://github.com/DeveloperAlly/claude-code-survival-toolkit)** — broader in-app survival kit for the VS Code extension: 9 fix scripts (sidebar dropped sessions, scrambled titles, scrambled sort order, vscode `state.vscdb` snapshot/restore) plus 7 governance hooks. macOS bash; use this if your data is on disk but the extension's sidebar is broken or scrambled.

**Linux:**
- **[vsits/restore-claude-history-linux](https://github.com/vsits/restore-claude-history-linux)** — Linux port of this tool. ZFS, Btrfs, and Timeshift all shipped (v1.1.0); real-kernel e2e validation on each. Recovery logic stays in lockstep with this repo via an upstream-sync workflow.

**Windows:**
- **[BasedGPT/claude-code-session-recovery](https://github.com/BasedGPT/claude-code-session-recovery)** — Windows-specific Claude Desktop metadata repair (orphan JSONLs, junction slug mismatches, missing groupings).

**Cross-platform:**
- **[ibrews/claude-session-recovery](https://github.com/ibrews/claude-session-recovery)** — your JSONLs are still on disk, but Claude Desktop's UI doesn't show them (index corruption after a crash/BSOD). Rebuilds the Desktop session index.
- **[markwoitaszek/claude-session-recovery](https://github.com/markwoitaszek/claude-session-recovery)** — Claude Desktop crashes with "There was a problem with the session" on a specific large/complex chat. Extracts the JSONL to clean Markdown so you don't lose the conversation.

## License

[MIT](LICENSE)
