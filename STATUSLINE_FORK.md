# Personal Codex status-line fork

For daily commands, updates, and recovery, start with [notes.md](notes.md).

`custom-main` is the default branch of `tbols2721/codex`. It contains the tested
OpenAI release plus explicit status-line rows. The original `main` branch is
retained. Do not use GitHub **Sync fork** on `custom-main`: update from a release
tag through a candidate branch instead.

The upstream base is recorded in `.statusline-upstream.json`. The first tested
build is tagged `statusline-tested-0.166.0`. The feature and the package lockfile
change are separate commits. The release version must remain a real OpenAI
release version; `0.0.0` can change model access and credential-store behavior.

## Local files

- Source: `/home/jbrennan/Research/codex-statusline`
- Scripts: `/home/jbrennan/Research/file.research.d/file.scripts.d/codex-statusline-maintenance`
- Script backup: the `statusline-maintenance` branch in this fork
- Personal settings: `~/.codex/config.toml` and `~/.codex/statusline-trial.config.toml`

Personal settings, login files, model caches, and compiled binaries are not
committed to Git. The scripts do not overwrite the personal status-line layout.

## Choose a CLI

Both commands are on PATH:

```sh
codex       # Official build
codexJoe    # Custom build with the saved three-row profile
```

`codexJoe` starts in your current directory. Runtime commands use
`statusline-trial` unless you select another profile with `--profile`. Plain
interactive sessions, `resume`, and `fork` use the local runtime. Utilities
such as `debug models` and `login` pass through to the custom CLI without added
runtime flags. `codexJoe update` checks for releases through the maintained
update tool; use the procedure below to build and promote an update.

Future sessions should read this checkout's `AGENTS.md`. A short pointer in
`~/.codex/AGENTS.md` makes it discoverable from other working directories. The
maintenance worktree also has its own `AGENTS.md` for script changes.

## Update procedure

Use `update.py` in the scripts directory. Run `python3 update.py --help` for
the commands and options.

1. Run `check` to read the latest stable OpenAI release.
2. Run `stage rust-vX.Y.Z` to merge that exact release into a new branch and
   checkout under `~/Research/codex-statusline-updates/`. This retains the custom
   commits and their history. It does not rebase or force-push `custom-main`.
3. If Git reports a conflict, resolve it in the candidate checkout. Inspect
   every resolution, regenerate workspace package versions in `Cargo.lock`,
   update `.statusline-upstream.json`, and commit the result. Do not discard
   custom changes with an automatic “theirs” resolution.
4. Install or extract the matching official release in a separate directory.
   Run `verify CANDIDATE --official-package PACKAGE`. This runs the focused
   Rust tests, builds the CLI, copies matching official helpers and resources
   into a separate package, and checks the model catalog and native model picker.
   It sends no inference request. A real request is a separate optional check.
5. Run the candidate package with `--no-daemon --profile statusline-trial` and
   check your layout. Run `promote CANDIDATE` after you accept it. Promotion
   requires a current verification receipt, saves a backup tag, fast-forwards
   `custom-main`, pushes to your fork, and switches the trial launcher to the
   verified package. It does not replace the normal `codex` command.

If a conflict or check fails, stop and fix the candidate. The working source
branch and trial executable remain in place. A new release can require changes
to the feature, Rust toolchain, test driver, or model identifier. No update
process can guarantee a conflict-free merge.

## Recovery

`python3 update.py rollback` switches the trial launcher to its previous package.
It leaves Git history in place. A later fixed release can then move forward
normally. Backup tags preserve the source before each promotion. Avoid resetting
or force-pushing `custom-main`.

To recover source on another machine, clone this fork and check out
`custom-main`. Check out the `statusline-maintenance` branch in your scripts
directory for the update tools. Change the command-line paths for another home
directory. Keep the matching official package available for build verification.
