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

The local command `codex-statusline-update` links to `update.py` here.
The local command `codexJoe` links to `codexJoe.py` here. It follows the
promoted custom binary, uses the saved trial profile for runtime commands,
and starts in the caller's current directory. An explicit `--profile` overrides
the default. `codex` continues to select the official CLI. `codexJoe update`
checks for releases with this maintenance tool.

```sh
codex-statusline-update check
codex-statusline-update stage rust-vX.Y.Z
codex-statusline-update verify ~/Research/codex-statusline-updates/X.Y.Z \
  --official-package /path/to/official/X.Y.Z/package
# Run the printed candidate command and check the result before promotion.
codex-statusline-update promote ~/Research/codex-statusline-updates/X.Y.Z
codex-statusline-update rollback
```

Global path/toolchain options must precede the command. For example:

```sh
codex-statusline-update --toolchain 1.97.1 verify ~/Research/codex-statusline
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

On a Git conflict, resolve it in the candidate checkout. Check the selected
release's workspace version, regenerate the workspace lockfile entries, update
`.statusline-upstream.json` with the printed release tag and commit, and commit
the merge. Re-run `verify` after every source change. A changed candidate commit
cannot reuse an old receipt. A newer upstream toolchain or model catalog can
require changes to these scripts; failed checks stop promotion.

Run the update workflow tests with `python3 test_update.py`. These tests use
temporary local repositories, not the user's fork. They check history retention,
conflict stops, stale receipts, binary and helper changes, fast-forward pushes,
initial adoption, failed writes, interrupted switches, and rollback.

The active `custom-main` and historical `statusline-maintenance` branches
retain their existing protection against force pushes and deletion. The
policy body is stored in `branch-protection.json`; it does not require a
PR or external CI.

To restore the tools on a new machine:

```sh
git clone --branch custom-main https://github.com/tbols2721/codex.git ~/Research/codex-statusline
git -C ~/Research/codex-statusline remote add upstream https://github.com/openai/codex.git
mkdir -p ~/.local/bin
ln -s ~/Research/codex-statusline/maintenance/codexJoe.py ~/.local/bin/codexJoe
ln -s ~/Research/codex-statusline/maintenance/update.py ~/.local/bin/codex-statusline-update
```

Create the links only when those command paths are unused. Adapt the script
defaults if the home directory differs. No extra worktree is needed. Build
outputs and verification receipts are local, so run verification again after
recovery. Keep personal configuration and login backups separate from this
public Git fork.
