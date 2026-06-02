# Host FS migration plan — snapshot-capable session storage on visits-01

Status: plan-stage
Driver: Recent unrecoverable loss of session files representing real engineering work. Backups are rebuildable; lost LLM context is not (it costs tokens == dollars to re-derive, and some context — verbal direction, intermediate reasoning — is not even rebuildable).
Tracking issue: TBD (file before execution).

## Goal

Bring the host's Claude Code session storage (`~/.claude/`) onto a filesystem that supports cheap, frequent, automatic snapshots — so that the `restore-claude-history-linux` tool's recovery path is actually available on the host the tool was written to protect. Today the host's `/` is ext4 with no snapshot capability; the tool has no source to recover from.

## Non-Functional Requirements

- **Size/complexity budget:** Plan-level estimate — ~10 commands to provision the array, ~5 to migrate data, ~3 to enable snapshots. No new code from RCB; all standard tooling. Heavyweight planning, lightweight implementation.
- **Threat model:** Migration window is the highest-risk moment (live data → moved data → bind-mounted back). Mitigated by (a) a tarball backup of `~/.claude` before any move, (b) the stopgap session-backup hook already in place writing to `/mnt/ssd`, (c) doing the migration with no active CC sessions, and (d) verifying CC works before deleting the original. Steady-state risk is one bad drive — addressed by RAID-10 fault tolerance + snapshot retention on a separate fault domain (see "Off-host backup" below).
- **Maintainability constraints:** No new tooling we don't already use elsewhere. Btrfs is what the v1.0.0 tool already covers; btrbk is a standard package. No custom snapshot scheduler.
- **Performance/reliability:** Spindle latency (~5–10 ms seek) vs SSD (~0.1 ms). CC's append-only jsonl writes are sequential and small (each turn appends ~kB); spindle latency is below human perception for this workload. The kanfei sim cache is a separate concern — it benefits from SSD, see "SSD repurpose" below.
- **Load-bearing? Yes.** This change affects the host's data path for every Claude Code project, the recovery-test surface the RCB tool was authored against, and a meaningful chunk of working memory. Adds Chris as a required approver before execution.

## Hardware available

| Device | Size | Type | Current use | Post-migration role |
|---|---|---|---|---|
| `sda` | 74.5 GB | SSD | LVM PV → `/` | Unchanged (system) |
| `sdb` | 74.5 GB | SSD | LVM PV → `/` | Unchanged (system) |
| `sdc` | 74.5 GB | SSD | LVM PV → `/` | Unchanged (system) |
| `sdd` | 74.5 GB | SSD | LVM PV → `/` | Unchanged (system) |
| `sde` | 1.8 TB | External SSD (exFAT) | `/mnt/ssd` — mixed scratch | Repurposed; see "SSD repurpose" |
| **New spindles ×4** | **4 × 1.2 TB** | HDD | (pending delivery, this week or next) | **Btrfs RAID-10 pool** |

## Architecture choice — Btrfs RAID-10

Three considered:

1. **Btrfs RAID-10 (chosen).** 4 × 1.2 TB → ~2.4 TB usable. Striped mirrors: tolerates **any single drive failure**, and depending on which pair, tolerates two failures. Reads scale across all 4 spindles (2× read throughput vs RAID-1). Writes go to two devices simultaneously (1× write throughput, fine for our workload). Snapshots are subvolume-based, instant, COW. `btrbk` provides retention scheduling.
2. **Btrfs RAID-1 (rejected).** Same fault tolerance as RAID-10 for the single-failure case, but RAID-10 wins on read parallelism and is no more complex to set up. Capacity is the same (~half the raw, both schemes).
3. **ZFS RAID-Z2 (rejected for this host).** ~2.2 TB usable, double-parity (tolerates any 2 drives failing). Stronger fault tolerance, native compression, world-class scrub semantics. But: (a) ZFS-on-Linux adds out-of-tree kernel modules on Ubuntu and one more thing to keep aligned with kernel updates, (b) the RCB v1.0.0 dogfood validation path is on Btrfs, so reusing that exact code path matters for tooling continuity, (c) the second-failure protection ZFS offers is worth less when we have off-host backup (see below). RAID-10 is the lighter-weight Btrfs option that still leaves room for ZFS if we ever change our mind (the pool can be wiped and rebuilt; the migration procedure stays identical).

> **Btrfs RAID-5/6 explicitly avoided.** The write-hole status remains "not for production" per the kernel docs even on 6.8. RAID-10 has no such caveat.

## Pool layout

```
/dev/sdf  ─┐
/dev/sdg  ─┤  Btrfs RAID-10  ─→  /mnt/data
/dev/sdh  ─┤  (subvolume layout below)
/dev/sdi  ─┘

/mnt/data/
├── @claude/                  # bind-mounted to ~/.claude
├── @claude-snapshots/        # btrbk writes snapshots here (sibling subvol)
├── @cache/                   # large reproducible caches (kanfei sim, etc.)
├── @archives/                # cold storage migrated from /mnt/ssd
└── @scratch/                 # working space, no snapshots
```

Subvolume strategy:
- `@claude` is its own subvolume so snapshots are scoped to just session data — they don't accidentally include the (large, reproducible) kanfei cache or archives.
- `@cache` and `@scratch` are subvolumes too so they can be explicitly excluded from any snapshot policy via btrbk config.
- Snapshots live in `@claude-snapshots/` as a sibling subvol; btrbk creates them there with timestamped names per its retention policy.

## Snapshot policy (btrbk)

```ini
# /etc/btrbk/btrbk.conf  (excerpt)
timestamp_format       long
snapshot_preserve_min  2h
snapshot_preserve      48h 14d 8w 12m

volume /mnt/data
  snapshot_dir @claude-snapshots
  subvolume @claude
```

Translated:
- Keep every snapshot for the last 2 hours (so a recent mistake has fine-grain recovery).
- Hourly snapshots for 48 hours.
- Daily snapshots for 14 days.
- Weekly snapshots for 8 weeks.
- Monthly snapshots for 12 months.

`btrbk run` fires from cron every 15 minutes; the retention logic prunes automatically. The `~/.claude` footprint is ~1 GB and grows slowly; even with COW + 12 months of retention we're well under 100 GB of snapshot overhead.

## SSD repurpose (the external 1.8 TB)

Once `~/.claude` and the kanfei cache are off `/mnt/ssd`, the external drive's role changes:

- **Off-host backup target for `@claude` snapshots.** `btrfs send | btrfs receive` from the spindle pool to a Btrfs partition on the SSD daily. This is the second fault domain — a controller failure on the pool can't take the off-host store with it. Note: requires reformatting `/mnt/ssd` from exFAT to Btrfs. The exfat contents are a mix of `$RECYCLE.BIN` cruft, large archives (the 12 GB jp60 image, the `Install Security for Mac.zip`), and the kanfei cache. We'd tarball the kept content first, reformat, restore.
- **Optional secondary scratch.** Whatever capacity isn't used for snapshot mirroring stays as a fast scratch space.

Alternative if you want to keep exFAT on `/mnt/ssd`: skip the off-host Btrfs-receive setup and just `rsync` snapshot trees nightly. Less elegant, less efficient (full rsync each time vs btrfs send's incremental), but no exfat→btrfs migration step.

## Migration procedure

Once the new drives are installed and visible as `/dev/sd{f,g,h,i}`:

### Pre-migration (no downtime)
1. **Verify drive identification.** `lsblk -d -o NAME,SIZE,MODEL,SERIAL` should show exactly 4 new 1.2 TB devices with matching models. Record serials in case a drive needs warranty replacement.
2. **SMART check.** `sudo smartctl -t short /dev/sd{f,g,h,i}`, wait, `sudo smartctl -a /dev/sd*` — confirm no DOA drives.
3. **Tarball-backup `~/.claude`.** `sudo tar --xattrs -cf /mnt/ssd/claude-pre-migration-$(date +%Y%m%d).tar ~/.claude && ls -la /mnt/ssd/claude-pre-migration-*` — the SSD's exFAT can hold it; this is the rollback if anything goes wrong.
4. **Confirm the stopgap session-backup hook ran recently.** `tail ~/.claude/session-backup.log` — most recent line should be within the last 5 minutes (cron is `*/5`).
5. **Idle the host.** Stop all CC sessions, the upstream-sync cron (`crontab -e` comment line out), the warmer cron, anything that touches `~/.claude/projects`. We want zero writes for ~5–10 minutes.

### Pool creation (~10 minutes)
6. **Create the Btrfs RAID-10 pool.**
   ```bash
   sudo mkfs.btrfs -L data -m raid10 -d raid10 /dev/sd{f,g,h,i}
   sudo mkdir -p /mnt/data
   sudo mount -t btrfs -o noatime,compress=zstd:3 /dev/sdf /mnt/data
   ```
   Compression is opt-in; zstd:3 is the standard balance. JSONLs compress 3–4×.
7. **Create subvolumes.**
   ```bash
   sudo btrfs subvolume create /mnt/data/@claude
   sudo btrfs subvolume create /mnt/data/@claude-snapshots
   sudo btrfs subvolume create /mnt/data/@cache
   sudo btrfs subvolume create /mnt/data/@archives
   sudo btrfs subvolume create /mnt/data/@scratch
   sudo chown -R manager:manager /mnt/data
   ```
8. **Populate `/etc/fstab`** so the pool auto-mounts on boot:
   ```
   UUID=<pool-uuid>  /mnt/data  btrfs  noatime,compress=zstd:3,subvolid=5  0 0
   ```
   The `subvolid=5` mount of the pool root (rather than a specific subvolume) lets bind mounts of subvolumes work below it.

### Data migration (~5 minutes for `~/.claude`, longer for caches)
9. **Copy `~/.claude` into the new subvolume:**
   ```bash
   rsync -aHAX --info=progress2 ~/.claude/ /mnt/data/@claude/
   ```
   `-aHAX` preserves perms, hard links, ACLs, xattrs. Don't use `cp -a` — rsync's progress output and resumability matter on the off chance the box hiccups mid-copy.
10. **Sanity-check** post-copy:
    ```bash
    diff -r --brief ~/.claude /mnt/data/@claude | head
    ```
    Should be empty. If anything diffs, stop and investigate before continuing.

### Bind-mount cutover (~30 seconds)
11. **Move old `~/.claude` aside (don't delete yet):**
    ```bash
    mv ~/.claude ~/.claude.pre-migration
    mkdir ~/.claude
    sudo mount --bind /mnt/data/@claude ~/.claude
    ```
12. **Make bind permanent in `/etc/fstab`:**
    ```
    /mnt/data/@claude  /home/manager/.claude  none  bind  0 0
    ```
13. **Verify Claude Code works.** Start a session in any cwd:
    ```bash
    cd ~/git_repos/restore-claude-history-linux && claude
    ```
    Then `/resume` — should list this session and others. Take one turn. Confirm a new jsonl appears under `/mnt/data/@claude/projects/<encoded-cwd>/`. Exit cleanly.

### Snapshot activation
14. **Install btrbk** (Ubuntu package): `sudo apt-get install -y btrbk`.
15. **Configure** `/etc/btrbk/btrbk.conf` per the policy above.
16. **Verify** with `sudo btrbk -n run` (dry-run); first real run with `sudo btrbk run`.
17. **Cron entry**: `*/15 * * * * /usr/bin/btrbk -q run`.

### Post-migration cleanup
18. **Re-enable** the upstream-sync cron, warmer, etc.
19. **Test the RCB tool against the new snapshots.** With one snapshot taken, delete a known jsonl from `@claude/projects/<test-dir>/`, run `restore_claude_history.py --backend btrfs --dry-run` — confirm it sees the snapshot and finds the file. (Actual restore optional — the dry-run validates the recovery path is live.)
20. **Wait 24 hours.** If the host has run through a full day of normal use without surprises, delete `~/.claude.pre-migration` and reclaim that ~1 GB on `/`.
21. **Update the stopgap hook to no-op.** The cron and SessionStart hooks can stay registered — they still provide off-pool defense in depth (and now write to a snapshotted FS too, which is harmless). Optional cleanup later if desired.

## Off-host backup (optional, recommended)

After the pool is stable and the SSD is reformatted to Btrfs (separately, in a calm window — this is not required for the migration to succeed):

```bash
# nightly, runs from cron
sudo btrfs send -p /mnt/data/@claude-snapshots/yesterday \
                  /mnt/data/@claude-snapshots/today | \
sudo btrfs receive /mnt/ssd-btrfs/@claude-mirror/
```

`btrfs send | receive` is incremental — only the diff between yesterday's and today's snapshots crosses the pipe. Daily cost: a few MB of session deltas, minimal SSD wear.

If the spindle pool's controller fails catastrophically, the SSD has the last 24 hours of state plus whatever retention policy we apply on its side.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Drive DOA after install | SMART check pre-pool-create; warranty replace before populating |
| Migration interrupted mid-rsync | Tarball backup #3 above; rsync is resumable |
| Bind mount breaks something CC depends on | `~/.claude.pre-migration` stays in place for 24h; revert is 3 commands |
| Snapshot policy too aggressive (fills the pool) | `btrfs filesystem usage /mnt/data` monitored via existing cron-watch infrastructure; alert at 75%, action at 85% |
| Single drive failure | RAID-10 keeps the pool live; `btrfs replace` resilvers in-place |
| Two-drive failure on wrong pair | RAID-10 best-case tolerates this, worst-case loses the pool — off-host backup is the second fault domain |
| Bit rot | Btrfs scrub via `sudo btrfs scrub start /mnt/data`; weekly cron, ~30 min on 2 TB |

## Out of scope

- Migrating `/` itself to a snapshot-capable FS. The system FS is fine on ext4; the data we care about is `~/.claude`.
- Migrating `~/git_repos/`. Repos have authoritative sources upstream (GitHub) and don't need snapshot-level rollback.
- Setting up automated off-host *off-site* backup (S3, B2, etc.). Out of scope for this plan; tracked separately if we want it.

## Acceptance criteria

- [ ] Pool created on `/dev/sd{f,g,h,i}` as Btrfs RAID-10, mounted at `/mnt/data`.
- [ ] `~/.claude` is a bind-mount of `/mnt/data/@claude`. CC sessions work. `/resume` finds historical sessions.
- [ ] btrbk runs from cron and accumulates snapshots in `@claude-snapshots`.
- [ ] `restore_claude_history.py --backend btrfs --list-backends` reports `available=true` with `snapshots > 0`.
- [ ] A test restore (delete-and-recover) succeeds against a real Btrfs snapshot on this host.
- [ ] (Optional, follow-up) SSD reformatted to Btrfs, off-host `btrfs send` running nightly.

## Triggering execution

Lead approval + Chris approval (Load-bearing? = Yes) before any drive is touched. Plan is executed by hand (operator commands per step), not via a script — the migration touches enough host-level state that human pacing matters more than mechanization.
