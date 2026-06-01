# TODO

Open work for this repo. Add as needed.

## Publicize the repo

Higher leverage than another feature — one well-placed comment lands in front of people *actively searching* right now. Do this before getting lost in new code.

Suggested order (lowest cost / highest signal first):

- [x] **1. Fill in `NOTES.md` → "Related GitHub issues" section.** Searched `anthropics/claude-code` for `cleanupPeriodDays`, `history deleted`, `lost chats`, `session not found`, `transcript missing`. Captured 16 threads grouped by priority in NOTES.md. *Done 2026-05-24.*

- [ ] **2. Comment on each of those issues.** 🟡 *In progress: 1 of ~16 posted (#59248 on 2026-05-24). Next up: #41458, then expand if traction. See NOTES.md checklist for the full ordered list.* Short, helpful, not spammy. Example:

   > Had this happen and built a recovery tool for it (macOS + Time Machine only): https://github.com/garrettmoss/restore-claude-history

   Don't post the same message verbatim everywhere; tweak per thread.

- [x] **3. File a new issue on `anthropics/claude-code`** if no good thread exists for it. Filed [#62272](https://github.com/anthropics/claude-code/issues/62272) on 2026-05-25 — "Chat JSONLs deleted from `~/.claude/projects/` despite `cleanupPeriodDays` set high — appears triggered by updates/restarts." Asks for any of: honor the setting, warn before deletion, surface in UI.

- [ ] **4. Reddit.** Candidates: r/ClaudeAI (most direct audience), r/MachineLearning (broader), r/macsysadmin (the Time Machine angle). One post per sub, spread over a few days. Title something like "Recovered months of deleted Claude Code chats from Time Machine — script + writeup".

- [ ] **5. Hacker News** (news.ycombinator.com). Submit as `Show HN: restore-claude-history – recover deleted Claude Code chats from Time Machine`. HN front page = hundreds of GitHub stars in a day; most submissions vanish. Low cost, asymmetric upside. Best times to submit: weekday mornings US time.

- [ ] **6. dev.to** — write a short post walking through the bug, the prevention setting, and how the recovery works. Indexed by Google long-term; useful for anyone searching "claude code chat history deleted" months from now.

- [ ] **7. Friends + personal network.** People who use Claude Code and might lose chats themselves — the prevention setting alone is worth sharing even if they never need the recovery.

- [ ] **8. Stretch: reach out to Anthropic directly.** If any of the above gets traction, that's leverage to ask Anthropic to link the tool from their docs or surface `cleanupPeriodDays` in the UI. The point isn't credit; it's preventing future users from hitting this in the first place.

Tip: track which channels actually drove traffic (GitHub repo Insights → Traffic) so future-you knows what worked.

## ~~Sequential mount/index/unmount refactor~~ (shipped v1.0.1, 2026-05-28)

Shipped sequential mount → index → restore → unmount in v1.0.1. Walks snapshots newest-first, dedupes (project, jsonl) pairs via a `seen` set in `main()` (relies on the JSONL append-only invariant: newest snapshot containing a file = largest version). Same for session subdirs — first writer wins.

**Partial improvement, not a cure.** Observed 2026-05-28 (4 snapshots, M-series Mac): no longer saw the 4-up CGPDFService line at 20–50% CPU each that the old parallel design produced — likely because we now only have one owned mount alive at any given moment. So the *concurrent* mount-time worker pile-up is genuinely reduced. But post-script, ~12 mdworker_shared + ~5 CGPDFService still spawned within 1s of exit with mds_stores at 60% CPU; best read is that the macOS-owned auto-mount (which is still mounted because we don't touch it) is what they're scanning. Sequential mounting bounded what *we* contributed; it can't quiet what the OS auto-mount keeps stirring up.

Why ship anyway: real reduction in concurrent worker count, simpler control flow, and the in-loop dedupe is a structural win regardless of Spotlight. Patch-version-only because the user-visible "CPU goes nuts when TM is plugged in" pain is still mostly there.

## ~~Local APFS snapshots as a primary recovery source~~ (shipped v1.1.0, 2026-05-28)

Shipped `--source=local|tm|both` (default `both`) in v1.1.0. With no TM drive plugged in, `find_tm_device()` now falls through silently and the script proceeds against local snapshots on `/System/Volumes/Data`. `find_data_root` handles the local-snapshot mountpoint layout (`<mp>/Users/...`, no `Data/` wrapper). Sequential mount loop merges both pools and sorts newest-first across the union; the `seen` dedupe still applies.

Bonus discovery: **mounting a local-volume snapshot does NOT trigger Spotlight reindex** — verified zero new mdworker_shared/CGPDFService workers post-mount (vs ~12+5 from a TM-drive mount). Apparently the live Data volume's existing index already covers the snapshot's blocks via APFS COW. So the local-snapshot path is both drive-free *and* Spotlight-quiet, captured in NOTES.md.

Reality check on coverage: Apple docs claim "hourly local snapshots, retained 24h," but that retention only kicks in if Time Machine runs automatically. Maintainer backs up manually and rarely — exactly one local snapshot exists on his machine, dated 2026-04-24, the date of his last manual backup. For users like him, local snapshots are "one extra recent safety net" rather than "rolling 24h coverage." Still useful — that snapshot caught everything he'd lost between then and the recovery work — just not the deep history.

Also shipped alongside: `--list-only` flag for machine-readable preview, and the test harness (`verify_restore.py`) now uses it to pick test files from the intersection of (on-disk) ∩ (in-snapshot) and assert restored size + mtime match the snapshot's, not the live file's.

## Quiet Spotlight on snapshot mounts (v1.2)

Real target: stop the post-unmount mdworker_shared / CGPDFService storm documented in v1.0.1's notes above. Deprioritized to v1.2 because local-snapshot support (v1.1) likely makes this a non-issue for the common case — most users won't even mount the TM drive once local snapshots cover recent deletions. Still worth fixing for the deep-history path.

NOTES.md gotcha line says `mdutil -i off` "reports success but the index restarts" — likely tried naively in a past session. Worth revisiting more carefully:

- `mdutil -i off <mountpoint>` called *immediately* after `mount_apfs`, before the walk. Confirm whether the "index restarts" behavior is on next mount or in-place.
- `.metadata_never_index` and `.metadata_never_index_unless_rootfs` placed at the mountpoint root before walking. NOTES.md says these "do nothing" — verify against current macOS; the docs may have been written against an older OS version.
- Mount options: `mount_apfs -o noexec,noatime` etc. — see if there's a noindex equivalent.
- Last resort: `tmutil addexclusion -p <mountpoint>` or Spotlight Privacy plist injection (sudo, persists across mounts — surprises users, document loudly).

When shipping: bump `__version__` to `1.2.0`, tag `v1.2.0`. Per CLAUDE.md, in-script version and latest git tag must match.

## Friendly Full Disk Access (FDA) error message

Today, if the terminal running [restore_claude_history.py](restore_claude_history.py) doesn't have Full Disk Access, `mount_apfs` fails with a cryptic `Operation not permitted` and the script keeps going (it's caught as a warn-and-skip in `mount_snapshot`). User sees the raw macOS error and no guidance.

Fix: in `mount_snapshot`, when `mount_apfs` fails and stderr contains `permission` (case-insensitive), print a clearer message before the existing warn and exit. Don't add a separate preflight check — `com.apple.TCC` probing adds a new failure mode unrelated to what we actually care about, and the real `mount_apfs` call is the only place this matters.

Suggested wording (keep `(Underlying error: ...)` so unrelated mount failures — typo'd snapshot name, missing device — still surface):

```
ERROR: Could not mount your Time Machine backup snapshot.

This usually means the terminal running this script doesn't have
Full Disk Access (FDA). Grant FDA to whatever terminal you are
running this from (Terminal.app, iTerm, VS Code, Cursor, etc.):

  System Settings → Privacy & Security → Full Disk Access → toggle on

Then re-run. (Underlying error: <captured mount_apfs stderr>)
```

Apply the same treatment in [tests/spotlight_harness.py](tests/spotlight_harness.py)'s mount call. Also worth a one-line note in README about needing FDA.

## Claude Desktop session recovery

The Claude Desktop app has an embedded Claude Code area that lists past sessions in its UI, but clicking them often shows **"Session not found on disk"** — same disappearing-chat problem as Claude Code CLI, different storage location.

Confirmed path: `~/Library/Application Support/Claude/claude-code-sessions/<group>/<project>/local_*.json` (verified 2026-05-27 — one group dir present on this machine with 11 `local_*.json` metadata entries).

Other adjacent dirs that may matter:
- `~/Library/Application Support/Claude/claude-code/`
- `~/Library/Application Support/Claude/claude-code-vm/`
- `~/Library/Application Support/Claude/local-agent-mode-sessions/`

### Subtask: metadata synthesis after a Time Machine restore

Raised by @BasedGPT on [#62272](https://github.com/anthropics/claude-code/issues/62272#issuecomment-4554894518) (and corroborated by @ShreeshaJay on [#48334](https://github.com/anthropics/claude-code/issues/48334)): JSONLs restored into `~/.claude/projects/` *without* a matching `local_*.json` entry in `claude-code-sessions/` get treated as orphans on the next cleanup pass and re-deleted. Originally observed on Windows; the path exists on macOS too, so the same risk almost certainly applies here.

This means the current `restore_claude_history.py` flow has a gap: a successful restore can be silently undone on the next sweep if metadata isn't synthesised alongside the JSONLs. Fixing this is the natural bridge into the broader Desktop recovery work below — same files, same machine, same investigation.

Reference implementation: [`BasedGPT/claude-code-session-recovery` → `tools/sessions/synth_session_metadata.py`](https://github.com/BasedGPT/claude-code-session-recovery/blob/main/tools/sessions/synth_session_metadata.py). Windows-targeted; logic ports. He gave permission to use it as the reference (and we gave him reciprocal permission on our largest-file + mtime-preservation code). Credit + link when this lands. I publicly committed to this being "next" in the [#62272 reply](https://github.com/anthropics/claude-code/issues/62272), so don't let it drift.

### Broader Desktop recovery — suggested approach for whoever picks this up
1. **Investigate first, code second.** Look at what's actually in those dirs, what file format the sessions use, and whether the UI is reading from the same place we'd be writing to. Don't assume it works like Claude Code's `~/.claude/projects/`.
2. **Compare against a Time Machine snapshot.** Mount a snapshot, compare the same dirs inside it to what's on disk now. The diff *is* the deleted content.
3. **Decide: extend `restore_claude_history.py` or write a sibling?** Depends on how similar the file layout and recovery logic are. If JSONLs in a parallel dir, probably one script with a `--desktop` flag. If wildly different format (SQLite, IndexedDB, encrypted blobs, etc.), a sibling script is cleaner.
4. **Start with `young-ladys-primer`.** It's the same project we used for the Claude Code recovery, so we know what "before" looks like and have a good chance of finding restorable data in the snapshots. The UI currently shows these chats with the title "Session not found on disk" and the subtitle "Send a message to start fresh in this directory" (along with "Archive" and "Delete" buttons — note: not "Recover"). Hopefully this is the more recoverable failure mode of the two.
5. **Then stress-test on `data-of-being`.** Its chats show "no messages yet" — a more severe failure mode. Possibly older than the available Time Machine snapshots, in which case this one may genuinely be unrecoverable. Useful either way: success expands the script's coverage, failure tells us where the floor is.

NOTES.md has the design rationale and gotchas from the Claude Code recovery work — most of the snapshot-handling, ACL-stripping, and mtime-preservation logic will carry over.

## Stretch: user-hosted Claude chat backups

A continuous, user-run backup of `~/.claude/projects/` so you don't have to rely on Time Machine (or any specific OS-level snapshot tool) to recover from a future deletion event.

- **Explicitly post-v1.** Ship the recovery tool, do the Desktop follow-up, *then* consider this. Easy to lose a week here.
- **Weakens the current pitch.** Today the script is "Time Machine + run this." Adding a backup feature means the story splits: "Time Machine, OR you installed our backup tool *before* the deletion." Most users won't have done the latter — so the recovery story stays cleaner if backups stay separate.
- **Probably a sibling project**, not a feature of this one. Different shape (daemon vs. one-shot), different audience (preventative vs. reactive).

**Starting point when we pick this up:** @ojura sketched a `SessionStart` hook on [#59248](https://github.com/anthropics/claude-code/issues/59248) — a small bash script that copies any `*.jsonl` from `~/.claude/projects/` to `~/.claude-session-backups/` on every session launch, only when the live file has grown (mtime-immune, shrink-safe). Wired in via `~/.claude/settings.json` under `hooks.SessionStart`. Worth using as the reference implementation for our `backup_claude_history.py` — credit ojura, then extend with: a real CLI, restore-from-backup verb, retention policy, optional macOS LaunchAgent for continuous (not just session-start) coverage, and cross-platform stat handling (his script already handles GNU vs. BSD `stat`). One concrete reason to prioritize this over "just set `cleanupPeriodDays: 36500`": per ojura, processes started with `--setting-sources local` or SDK sessions with `settingSources: []` (including autonomously spawned subagents) bypass the setting and fall back to the 30-day default. A SessionStart-driven backup sidesteps that whole class of bypass.
