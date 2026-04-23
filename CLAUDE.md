# Repository Rules

## Pull Requests
- When a pull request changes source code, increment the version number as part of the PR. Skip the bump for PRs that only touch docs, config, CI, or similar non-source changes.

## Branch Hygiene
- Keep working branches regularly updated from the main branch (fetch + merge/rebase from `main`) while work is in progress.
- Assume the user may commit changes to the branch while you are working on it. Before editing, fetch and integrate any new commits from the remote, and re-check file contents rather than relying on earlier reads.

## Issue Tracking
- Track reported bugs and feature requests as GitHub issues in the repo's tracker. When the user describes a bug, open an issue for it (unless one already exists).
- When opening a PR that addresses an existing issue, include `Fixes #N` (or `Closes #N`) in the PR description so GitHub auto-closes the issue on merge.
- If a PR that addresses an issue is merged without the auto-close keyword, close the issue manually and link back to the merged PR.
- Mark every issue you file with a footer line `_Filed by Claude Code._` at the end of the body, so user-filed issues stay visually distinct from Claude-filed ones.
- Do not pick up or attempt to fix issues that the user created unless the user explicitly asks for it. Claude-filed issues are fair game to work on when in scope.
