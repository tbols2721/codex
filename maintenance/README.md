# Codex status-line maintenance

This directory stores the maintained update scripts on `custom-main`, beside
the fork source. The user approved this exception to the general script
location rule on November 3, 2026. Commit source, scripts, and related notes
together. Do not commit personal configuration or credentials.

The old `statusline-maintenance` branch history was imported here. That
branch is retained as history and has no active worktree. The copy under
`file.scripts.d/codex-statusline-maintenance` is an independent reference
snapshot: ordinary files, no `.git`, symlinks, or automatic sync. Installed
commands do not use the snapshot.

The regular commands `codex-statusline-update` and `codexJoe` run installed
maintenance copies under `~/.local/share/codex-statusline/maintenance`. The
launcher reads the promoted package from installation state and uses the saved
trial profile for runtime commands,
and starts in the caller's current directory. An explicit `--profile` overrides
the default. `codex` continues to select the official CLI. `codexJoe update`
checks for releases with this maintenance tool.

```sh
codex-statusline-update check
codex-statusline-update stage rust-vX.Y.Z
codex-statusline-update verify ~/Research/worktrees/codex-statusline/X.Y.Z \
  --official-package /path/to/official/X.Y.Z/package
# Run the printed candidate command and check the result before promotion.
codex-statusline-update promote ~/Research/worktrees/codex-statusline/X.Y.Z
codex-statusline-update rollback
```

Global path/toolchain options must precede the command. For example:

```sh
codex-statusline-update --toolchain 1.97.1 verify ~/Research/file.private-repos/codex-statusline
```

`verify` requires a complete matching official package: `bin/codex`,
`bin/codex-code-mode-host`, and its resources. It copies that package outside
the official updater cache, then replaces its CLI with the custom build. The
tests use the saved login. Credential overrides are removed only from test child
processes. The verifier sends no inference request unless separately requested
with `verify_codex_statusline_runtime.py --inference`.

`promote` requires a receipt for the current commit and unchanged executable,
helpers, resources, and file modes. It
backs up the old source with a tag, pushes a normal fast-forward to the fork,
and switches only the trial executable. It does not install a normal `codex`
command. `rollback` switches the trial executable back and retains Git history.
Do not delete packages referenced in `~/.codex/statusline-maintenance/installation.json`.
The first promotion preserves the existing trial binary and its matching
official resources. A journal makes an interrupted executable/state switch
recoverable on the next update command.

On a Git conflict, resolve it in the candidate clone. Check the selected
release's workspace version, regenerate the workspace lockfile entries, update
`.statusline-upstream.json` with the printed release tag and commit, and commit
the merge. Re-run `verify` after every source change. A changed candidate commit
cannot reuse an old receipt. A newer upstream toolchain or model catalog can
require changes to these scripts; failed checks stop promotion.

Run the update workflow tests with `python3 test_update.py`. These tests use
temporary local repositories, not the user's fork. They check history retention,
conflict stops, stale receipts, binary and helper changes, fast-forward pushes,
annotated release tags, initial adoption, failed writes, interrupted switches,
and rollback.

The active `custom-main` and historical `statusline-maintenance` branches
retain their existing protection against force pushes and deletion. The
policy body is stored in `branch-protection.json`; it does not require a
PR or external CI.

To restore the tools on a new machine:

```sh
git clone --branch custom-main https://github.com/tbols2721/codex.git ~/Research/file.private-repos/codex-statusline
git -C ~/Research/file.private-repos/codex-statusline remote add upstream https://github.com/openai/codex.git
python3 ~/Research/file.private-repos/codex-statusline/maintenance/install_commands.py
```

The installer writes regular command files and maintenance copies. It does not
modify the official CLI, personal profiles, or selected executable package.
Update candidates have their own Git metadata. Build
outputs and verification receipts are local, so run verification again after
recovery. Keep personal configuration and login backups separate from this
public Git fork.

Packages and verification receipts are specific to a machine and architecture.
For a move from ARM64 to x86-64, retain the source history and build again with
the destination's matching official helpers. Do not copy the ARM64 launcher
target, installation state, or old receipt into an x86-64 installation. Install
Rust and `tmux` before running `verify`; load `~/.cargo/env` when needed.
