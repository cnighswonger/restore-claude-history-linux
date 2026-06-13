Codex review: REQUEST_CHANGES for PR #33.

# Review: PR #33 — docs: v1.2 port directive (script rename) + boundary tightening

Date: 2026-06-12
Reviewed: `AGENTS.md`, `docs/directives/rcb-v1.2-rename-restore-claude-code-2026-06-12.md` at `87417e8df916722e0f814a643374f116ac901b2a`
Round: 1
Label applied: needs-changes

## Findings

| Severity | Path | Summary |
|---|---|---|
| High | `docs/directives/rcb-v1.2-rename-restore-claude-code-2026-06-12.md:22`, `docs/directives/rcb-v1.2-rename-restore-claude-code-2026-06-12.md:40`, `docs/directives/rcb-v1.2-rename-restore-claude-code-2026-06-12.md:93` | The reference-counting and acceptance-check story is internally inconsistent. Section 2 enumerates 13 update-target files and 22 planned replacements, but the NFR claims the same grep-based survey produced "~20 reference updates across 11 files". At commit `87417e8df916722e0f814a643374f116ac901b2a`, `git ls-files '*.py' '*.md' '*.sh' \| xargs grep -n "restore_claude_history"` returns 31 hits across 15 tracked files: the 13 listed targets, plus `restore_claude_history.py` itself and the new v1.2 directive. The validation rule is also impossible as written: it exempts only pre-rename directives, while the new v1.2 directive intentionally preserves eight `restore_claude_history` mentions, and it is ambiguous about older directives because Section 2 says to update two of them while Validation says pre-rename directives may intentionally retain the historical name. |
| High | `docs/directives/rcb-v1.2-rename-restore-claude-code-2026-06-12.md:62`, `tests/e2e/run.sh:273`, `tests/integration/test_zfs_real.py:18`, `tests/integration/test_btrfs_real.py:20`, `tests/integration/test_timeshift_real.py:24` | The QEMU section points the implementation PR at the wrong file. `tests/e2e/run.sh` does not invoke `restore_claude_history.py` by path; it shells into the VM and runs backend-specific pytest targets. The rename matters there through the integration-test imports, so the directive should require a harness rerun after the import/path updates, not an edit to `tests/e2e/run.sh`, unless a real path-based invocation is identified elsewhere. |

## What Is Correct

- The directive includes the full standard NFR checklist, and `Load-bearing? No` is the right classification for this docs-only planning PR and for the planned leaf-script rename.
- The no-shim/no-symlink deprecation policy is internally consistent with the migration hint. The release body is the migration surface; the directive does not promise a compatibility wrapper.
- The boundary edit in `AGENTS.md:210` is clear. It marks upstream Desktop tooling as `skip` for this repo's upstream-sync triage without closing the door on a separate future Linux-Desktop project.

## Blockers

1. The directive's counted scope and acceptance rule need to be rewritten so the implementation PR has a target a reviewer can actually verify.
2. The QEMU section needs to stop naming `tests/e2e/run.sh` as an expected edit unless the repo contains a real path-based invocation there.

## What Needs Attention

- The rollback plan is mechanically coherent, but a `linux/v1.2.1` revert would rename the entrypoint a second time. If that rollback path stays, the eventual release notes should call out that second migration explicitly.
- `TODO.md:48` and `TODO.md:55` still frame Desktop recovery as a possible extension of this repo. This PR does not need to resolve that older planning text, but the new boundary rule makes the mismatch more visible.

## Bloat / Non-Functional

None.

## Recommendations

- Update the size/complexity budget with repo-verified numbers and make the counting method explicit: literal grep hits, touched files, or human-visible reference edits.
- Rewrite the validation rule so it matches the intended allowlist. For example: zero hits outside an explicit set of historical/design documents, or zero hits across a concrete implementation-file list rather than the whole repo.
- Rewrite the QEMU section to say "rerun the harness after the import/path updates" unless a companion script with a literal `restore_claude_history.py` path is found.

## Bottom Line

The direction is sound: the NFR rubric is present, `Load-bearing? No` is correct, the no-shim migration stance is coherent, and the AGENTS boundary edit is clear. But this directive is the design surface for the follow-on implementation PR, and right now it contains two factual errors that would make that PR harder to execute and harder to verify. Fix the counting/validation language and the incorrect QEMU-file target, then re-request review.
