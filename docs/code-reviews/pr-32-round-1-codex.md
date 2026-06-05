Codex review:

# Review: PR #32 AGENTS.md slim-to-global

Date: 2026-06-05
Reviewed: `AGENTS.md` at `c3f6664607d5e529216e283a1f47f415af497a91`
Round: 1
Label applied: approved-by-codex-agent

## What Is Correct
- The new header correctly makes `~/.codex/AGENTS.md` the first-read Codex baseline while keeping this file as the repo-specific overlay. `AGENTS.md:5`
- The Codex review triggers section removes only cross-repo mechanics and keeps the RCB-specific rules that still belong here: all PRs require Codex review, the PR-body inline summary, the `vsits-codex-reviewer[bot]` identity, and the repo-specific artifact-path override. `AGENTS.md:97` `AGENTS.md:101` `AGENTS.md:105`
- The NFR section is now scoped correctly as author guidance, while reviewer-side anti-bloat, `Load-bearing?` validation, and citation discipline now live in the global baseline. The upstream-sync variant and human-backstop rule remain intact. `AGENTS.md:107` `AGENTS.md:119` `AGENTS.md:141`
- The public-repo containment rules, three-bot identity model, token-leak containment, label state machine with `needs-human-review` hard-stop, external-triage rules, boundary discipline, and upstream-sync workflow all remain present and operational. `AGENTS.md:30` `AGENTS.md:60` `AGENTS.md:89` `AGENTS.md:145` `AGENTS.md:182` `AGENTS.md:213` `AGENTS.md:229`
- `docs/code-reviews/` was not present in repo history before this round, but the override in `AGENTS.md:105` is explicit and unambiguous; this review artifact establishes that path on the PR branch.

## Blockers
None.

## What Needs Attention
None.

## Bloat / Non-Functional
None.

## Recommendations
None.

## Bottom Line
Ship it. This PR removes duplicated cross-repo Codex review mechanics, keeps the RCB-specific governance that still needs to live in-repo, and leaves the directive-author NFR rubric internally consistent with the new global baseline.
