# Codex status-line maintenance

This branch stores the local update scripts. It is a separate Git worktree in
the required scripts directory. The source lives on `custom-main` in the same
fork. Neither branch contains personal configuration or credentials.

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

The fork's `custom-main` and `statusline-maintenance` branches disallow force
pushes and deletion through GitHub branch protection. The policy body is stored
in `branch-protection.json`; it does not require a PR or external CI.

To restore the tools on a new machine:

```sh
git clone --branch custom-main https://github.com/tbols2721/codex.git ~/Research/codex-statusline
git -C ~/Research/codex-statusline remote add upstream https://github.com/openai/codex.git
git -C ~/Research/codex-statusline worktree add \
  /home/jbrennan/Research/file.research.d/file.scripts.d/codex-statusline-maintenance \
  statusline-maintenance
```

Adapt paths if the home directory differs. The local command is an executable
symlink to this directory's `update.py`. Build outputs and verification receipts
are local, so run verification again after recovery. Keep personal configuration
and login backups separate from this public Git fork.
