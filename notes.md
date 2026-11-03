# Joe's Codex notes

These are practical notes for using and maintaining `codexJoe`. Codex should
keep this file current when commands, settings, or update steps change.

## Choose which build to run

Both commands are on your PATH and work from your current directory:

```sh
codex       # Official OpenAI build
codexJoe    # Custom build with your saved status-line rows
```

`codexJoe` uses your `statusline-trial` profile for runtime commands. Plain
interactive sessions, `resume`, and `fork` run locally. To choose a different
profile, use `codexJoe --profile NAME`.

Use `/statusline` inside `codexJoe` to assign fields to rows. Move **Start next
line** markers to choose the row boundaries. Each row truncates independently
when the terminal gets narrow.

## Update codexJoe

First, check for a new stable release:

```sh
codexJoe update
```

This command checks for releases. Installing one uses the build and test steps
below. If the current and latest versions match, no release update is needed.

When a newer release is available, replace every `X.Y.Z` below with its version.

1. Update the official CLI to obtain the matching helper programs and resources:

   ```sh
   codex update
   ```

2. Merge the selected release into a separate candidate branch and checkout:

   ```sh
   codex-statusline-update stage rust-vX.Y.Z
   ```

   If this reports a conflict or other failure, stop here and have Codex resolve
   the candidate. Your existing custom build stays available.

3. Build and test the candidate:

   ```sh
   codex-statusline-update verify ~/Research/codex-statusline-updates/X.Y.Z
   ```

   This uses the installed official package by default. Its version must match
   the candidate. To use another matching package, add
   `--official-package /path/to/package`. The build can take several minutes.
   A failed check stops promotion.

4. Run the candidate command printed by `verify`. Check your rows and `/model`.

5. Once you accept the candidate, make it the version that `codexJoe` launches:

   ```sh
   codex-statusline-update promote ~/Research/codex-statusline-updates/X.Y.Z
   ```

Promotion saves a backup source tag, pushes the changes to your fork, and selects
the tested custom package. Restart `codexJoe` to use that package in a new session.
The existing running session keeps its current executable.

## Return to the previous build

```sh
codex-statusline-update rollback
```

This selects the previous saved package for new `codexJoe` sessions. Git history
stays in place. Keep the current and previous packages until you no longer need
that recovery option.

## Where your settings and changes live

| Item | Location |
| --- | --- |
| Source and these notes | `~/Research/codex-statusline` |
| Official base settings | `~/.codex/config.toml` |
| Custom profile and saved rows | `~/.codex/statusline-trial.config.toml` |
| Custom executable packages | `~/.local/lib/codex-statusline/` |
| Update and rollback state | `~/.codex/statusline-maintenance/installation.json` |
| Maintained scripts | `~/Research/file.research.d/file.scripts.d/codex-statusline-maintenance/` |

The fork is [tbols2721/codex](https://github.com/tbols2721/codex).
`custom-main` is the default source branch. `statusline-maintenance` stores the
scripts. Both are protected against force pushes and branch deletion.

Use the update commands above to bring in OpenAI releases. GitHub **Sync fork**
is not the update procedure for `custom-main`.

Git backs up committed source, scripts, and documentation. Personal settings,
login files, caches, and compiled binaries are excluded. Keep a separate private
backup of settings you want to retain. Do not put login files or tokens in the
public fork.

For the full maintenance procedure, see [STATUSLINE_FORK.md](STATUSLINE_FORK.md).
[AGENTS.md](AGENTS.md) holds the handoff instructions for future Codex sessions.
