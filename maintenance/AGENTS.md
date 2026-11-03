# Codex status-line maintenance handoff

Read `/home/jbrennan/Research/codex-statusline/AGENTS.md` first. It holds the
project history, user requirements, paths, and update policy. Then read this
worktree's `README.md` and the source checkout's `STATUSLINE_FORK.md`.
Read and maintain `/home/jbrennan/Research/codex-statusline/notes.md` when script
changes affect commands, configuration, update steps, or recovery information
Joe needs. Commit those user-facing notes in the source worktree.

This directory is part of the `custom-main` checkout in `tbols2721/codex`.
The user approved an exception to the general script-location rule on
November 3, 2026: maintain these scripts here. Commit and push scripts,
source, and related notes together on `custom-main`. Do not commit personal
configuration or secrets.

The old `statusline-maintenance` branch is retained as history. Its history
was imported into `maintenance/`; it has no active worktree. The plain copy
under `file.scripts.d/codex-statusline-maintenance` is an independent reference
snapshot. Do not develop or run maintenance there, create command links to
it, or add automatic synchronization.

- `codexJoe.py`: PATH launcher. Preserve caller cwd, argv, environment, explicit
  profile selection, and subcommand-aware defaults. It follows the promoted
  binary symlink so promotion and rollback also change what `codexJoe` runs.
- `update.py`: exact-release staging, verification, promotion, and rollback.
  Resolve path arguments; leave conflicts in the candidate; preserve Git
  history; push the selected release tag with the source and backup tags.
- `test_update.py`: temporary local Git repositories. It checks history,
  conflicts, stale receipts, package integrity, first adoption, failed switches,
  interrupted switches, and rollback. It does not use the real fork.
- `verify_codex_statusline_runtime.py`: matching official/custom versions and
  catalogs. Inference is off by default. Keep credentials out of output.
- `smoke_test_codex_statusline_model.py`: disposable profile and private tmux
  server. Preserve real config bytes and remove only resources this run owns.
- `branch-protection.json`: blocks force pushes and deletion on the maintained
  branches without requiring a PR or external CI.

`pending-switch.json` is a recovery journal, not a file to delete casually.
`recover_switch` must align the actual selected executable and the saved state,
including an interrupted first archive of a regular legacy executable.
Pin executable modes and helper/resource hashes, not only CLI bytes.
Never overwrite the current package before the candidate passes checks.

Run `python3 test_update.py` for changes to Git, package, state, or recovery
logic. For a launcher change, check argument routing with harmless native
commands and confirm caller cwd. Do not submit a natural-language prompt as a
smoke test. Do not rebuild Rust for script or documentation changes alone.
