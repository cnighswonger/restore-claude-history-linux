# TODO

Open work for this repo. Add as needed.

## Claude Desktop session recovery

The Claude Desktop app has an embedded Claude Code area that lists past sessions in its UI, but clicking them often shows **"Session not found on disk"** — same disappearing-chat problem as Claude Code CLI, different storage location.

Likely path (needs verification):
`~/Library/Application Support/Claude/claude-code-sessions/`

Other adjacent dirs that may matter:
- `~/Library/Application Support/Claude/claude-code/`
- `~/Library/Application Support/Claude/claude-code-vm/`
- `~/Library/Application Support/Claude/local-agent-mode-sessions/`

Suggested approach for whoever picks this up:
1. **Investigate first, code second.** Look at what's actually in those dirs, what file format the sessions use, and whether the UI is reading from the same place we'd be writing to. Don't assume it works like Claude Code's `~/.claude/projects/`.
2. **Compare against a Time Machine snapshot.** Mount a snapshot, compare the same dirs inside it to what's on disk now. The diff *is* the deleted content.
3. **Decide: extend `restore_claude_history.py` or write a sibling?** Depends on how similar the file layout and recovery logic are. If JSONLs in a parallel dir, probably one script with a `--desktop` flag. If wildly different format (SQLite, IndexedDB, encrypted blobs, etc.), a sibling script is cleaner.
4. **Start with `young-ladys-primer`.** It's the same project we used for the Claude Code recovery, so we know what "before" looks like and have a good chance of finding restorable data in the snapshots. The UI currently shows these chats with the title "Session not found on disk" and the subtitle "Send a message to start fresh in this directory" (along with "Archive" and "Delete" buttons — note: not "Recover"). Hopefully this is the more recoverable failure mode of the two.
5. **Then stress-test on `data-of-being`.** Its chats show "no messages yet" — a more severe failure mode. Possibly older than the available Time Machine snapshots, in which case this one may genuinely be unrecoverable. Useful either way: success expands the script's coverage, failure tells us where the floor is.

NOTES.md has the design rationale and gotchas from the Claude Code recovery work — most of the snapshot-handling, ACL-stripping, and mtime-preservation logic will carry over.
