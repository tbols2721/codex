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
   codex-statusline-update verify ~/Research/worktrees/codex-statusline/X.Y.Z
   ```

   This uses the installed official package by default. Its version must match
   the candidate. To use another matching package, add
   `--official-package /path/to/package`. The build can take several minutes.
   A failed check stops promotion.

4. Run the candidate command printed by `verify`. Check your rows and `/model`.

5. Once you accept the candidate, make it the version that `codexJoe` launches:

   ```sh
   codex-statusline-update promote ~/Research/worktrees/codex-statusline/X.Y.Z
   ```

Promotion saves a backup source tag, pushes the changes to your fork, and selects
the tested custom package. Restart `codexJoe` to use that package in a new session.
The existing running session keeps its current executable.

## Upstream base: 0.169.0

This source uses [OpenAI release 0.169.0](https://github.com/openai/codex/releases/tag/rust-v0.169.0).
The built-in status line keeps your explicit rows with the release's new footer
layout. Each row truncates independently; a narrow terminal does not move fields
to another row. Empty rows remain in place. Input and active hints take priority
when the terminal is too short to show all rows.

The release puts the Plan mode indicator in the bottom hint row. The built-in
status line uses native rendering and supports theme colors. Extension-provided
status content uses the release's prepared UI renderer.

## Moving between machines

The upstream base is recorded in `.statusline-upstream.json`. The custom build
keeps explicit rows with the native and extension renderers, including
pull-request links and empty rows.

Compiled packages are specific to the processor architecture. Build again on
the destination with its matching official package. Keep its saved login and
personal settings local. Copying this repository does not synchronize profiles,
folder trust, compiled packages, or installation state.

A first custom installation has no previous package for `rollback`. A later
promotion retains the old local package. Check the local installation state
before using recovery commands; another machine can have a different version.

Building requires Rust, a C/C++ compiler, and the development libraries required
by the selected release. The native UI test also requires `tmux`. The tested
Rust toolchain is 1.97.1. Run `. "$HOME/.cargo/env"` if a shell cannot find
`cargo`.

Source updates are pushed to the fork. Other checkouts and running packages
stay at their previous versions until those machines are updated.

## Return to the previous build

```sh
codex-statusline-update rollback
```

This selects the previous saved package for new `codexJoe` sessions. Git history
stays in place. Keep the current and previous packages until you no longer need
that recovery option.

## API credit-offer MCP warning

On November 3, 2026, the optional `openai-api-credit-promo` server in the OpenAI
Developers plugin failed at startup with HTTP 403. A check of its endpoint
returned `cf-mitigated: challenge`, which identifies a Cloudflare security
challenge. The remote endpoint remains blocked; the local mitigation skips
that optional connection.

The following setting is now in `~/.codex/config.toml`:

```toml
[plugins."openai-developers@openai-curated-remote".mcp_servers."openai-api-credit-promo"]
enabled = false
```

This applies to new sessions that load the base config, including `codexJoe`.
Credit-offer tools are unavailable while this connection is disabled. The rest
of the plugin stays enabled. A fresh `codexJoe` session started without the
warning; `/mcp` showed this server as disabled and the local API-key confirmation
server as connected. Your custom profile and saved rows were preserved.

Restart `codexJoe` to load the setting. To try credit offers again after the
endpoint works, change this entry to `enabled = true` and restart. The warning
can return if the endpoint still blocks the connection. Do not edit the cached
plugin files; updates can replace them.

A private backup of the previous base config is stored beside it as
`config.toml.before-credit-promo-disable.Z0WWMP`.

## Local directory organization

This checkout is in `~/Research/file.private-repos/codex-statusline`.
Update candidates are independent clones under
`~/Research/worktrees/codex-statusline/<version>`. The maintenance defaults and
commands in these notes use those paths. Use `--source PATH` before a
maintenance subcommand when the source is elsewhere.

The command files in `~/.local/bin` are regular launchers. They run installed
maintenance copies in `~/.local/share/codex-statusline/maintenance`. The runtime
launcher reads the promoted package from
`~/.codex/statusline-maintenance/installation.json`, so moving a source checkout
does not break normal `codexJoe` commands. After changing maintained scripts,
refresh the installed copies with:

```sh
python3 maintenance/install_commands.py
```

Staged update candidates are independent Git clones with their own objects.
They can move without invalidating a shared worktree pointer. Promotion imports
the candidate commit into the source repository before checking ancestry and
pushing it. Use `--source PATH` before the maintenance subcommand if you move
the source away from its default location.

A verification receipt applies to one candidate commit and its package files.
If a candidate receives more source or maintenance changes, run verification
again before promotion. Keep current and previous packages listed in local
installation state.

## Where your settings and changes live

| Item | Location |
| --- | --- |
| Source and these notes | `~/Research/file.private-repos/codex-statusline` |
| Official base settings | `~/.codex/config.toml` |
| Custom profile and saved rows | `~/.codex/statusline-trial.config.toml` |
| Custom executable packages | `~/.local/lib/codex-statusline/` |
| Update and rollback state | `~/.codex/statusline-maintenance/installation.json` |
| Maintained scripts | `~/Research/file.private-repos/codex-statusline/maintenance/` |
| Independent reference copy | `~/Research/file.research.d/file.scripts.d/codex-statusline-maintenance/` |

The fork is [tbols2721/codex](https://github.com/tbols2721/codex).
`custom-main` is the active branch for both source and maintenance scripts.
On November 3, 2026, the maintenance branch history was imported into
`maintenance/`. The old `statusline-maintenance` branch remains as history;
it has no active worktree. Both branches retain their existing protection.

The maintained Codex scripts are an approved exception to the general script
location rule. Their source stays in this repository. Installed commands use
independent copies under `~/.local/share/codex-statusline`; refresh them with
`python3 maintenance/install_commands.py` after a script change. Commit script
and source changes, with these notes, on `custom-main`.

The reference copy under `file.scripts.d` contains ordinary files. It has no
`.git` file, symlinks, or automatic sync. The commands do not use it. Do not
run its scripts to maintain the fork. Its `SNAPSHOT.json` records the copied
source commit; later changes to the active scripts do not update this copy.

Use the update commands above to bring in OpenAI releases. GitHub **Sync fork**
is not the update procedure for `custom-main`.

Git backs up committed source, scripts, and documentation. Personal settings,
login files, caches, and compiled binaries are excluded. Keep a separate private
backup of settings you want to retain. Do not put login files or tokens in the
public fork.

For the full maintenance procedure, see [STATUSLINE_FORK.md](STATUSLINE_FORK.md).
[AGENTS.md](AGENTS.md) holds the handoff instructions for future Codex sessions.
