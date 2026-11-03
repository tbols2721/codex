# Codex status-line fork: session handoff

## User instructions

- Write clear, direct English, about 80% of the way to ASD-STE100.
- General rule: save scripts under
  `/home/jbrennan/Research/file.research.d/file.scripts.d/`.
- User-approved exception (November 3, 2026): maintain Codex fork scripts
  in this checkout under `maintenance/`, on `custom-main`. The copy under
  `file.scripts.d/codex-statusline-maintenance` is an independent reference
  snapshot. It has no Git worktree link, command links, or automatic sync.
  Do not develop the fork or run maintenance from that snapshot.
- Work on this fork in its own directory under `~/Research`. Do not develop it
  inside `file.research.d` or modify the reference checkout in `~/Git`.
- Carry out authorized local work. Ask only when a material choice is unresolved.
- Keep user edits to configuration and status-line rows. Do not reset them to a
  test fixture. User-specific configuration belongs under `~/.codex`.

## Notes for Joe

Read `notes.md` at the start of work on this project. It is the user-facing
record of commands, settings, update steps, recovery options, and limitations
Joe should know. Keep it current when work changes any of those details. Write
practical instructions there; keep agent handoff and implementation detail in
this file or the maintenance guide. Replace obsolete instructions instead of
leaving conflicting advice. Do not put credentials or private configuration in
the notes. Commit and push notes with the related changes to the user's fork.

## What this project does

This is Joseph Brennan's Codex CLI fork. It adds explicit status-line rows.
The user chooses which fields go on each row; automatic text wrapping does not
meet the requirement.

`tui.status_line` is a flat array with repeated `"line-break"` entries. The
`/statusline` picker shows movable **Start next line** entries. Alt+Enter adds
another marker when the key binding permits it. Rows truncate independently
when the terminal narrows. Preserve the picker preview, empty rows, save/cancel,
colors, warning geometry, and fullscreen/scrollback behavior. Normalize field
newlines so only configured markers make rows.

The user currently has three rows in the trial profile. Read that file if
needed; do not copy a stale layout from these notes over it.

## Commands and paths

- `codex`: official CLI, linked through `~/.codex/packages/standalone/current`.
- `codexJoe`: custom launcher on PATH at `~/.local/bin/codexJoe`. Its script is
  `maintenance/codexJoe.py` in this checkout. It starts in the caller's cwd.
- `codex-statusline-update`: the maintenance `update.py` command on PATH.
- Source: `/home/jbrennan/Research/codex-statusline`.
- Reference only: `/home/jbrennan/Git/openai-codex`.
- Maintained scripts: `/home/jbrennan/Research/codex-statusline/maintenance`.
- Independent reference snapshot:
  `/home/jbrennan/Research/file.research.d/file.scripts.d/codex-statusline-maintenance`.
- Candidate worktrees: `~/Research/codex-statusline-updates/<version>`.
- Custom packages: `~/.local/lib/codex-statusline/<version>-<commit>-<id>`.
- Promoted binary selector: this checkout's `bin/codex-statusline` symlink.
- Active base config: `~/.codex/config.toml`.
- Custom runtime profile: `~/.codex/statusline-trial.config.toml`.
- Local update state: `~/.codex/statusline-maintenance/installation.json`.
- Verification receipts: `~/.codex/statusline-maintenance/verified/`.

The launcher defaults runtime commands to `statusline-trial`. Plain TUI,
`resume`, and `fork` use `--no-daemon`, so the custom session runs locally.
An explicit `--profile` takes precedence. Explicit remote sessions retain native
remote behavior. `agents` requires a daemon and must not get `--no-daemon`.
Utility commands, such as `debug models`, `login`, and `completion`, do not
accept the same runtime flags. Preserve the launcher's command routing.
`codexJoe update` checks releases through the custom maintenance tool; it does
not invoke the official installer. Do not replace the official `codex` command.

## Git and durable backup

- `origin`: `https://github.com/tbols2721/codex.git`.
- `upstream`: `https://github.com/openai/codex.git`.
- `custom-main`: maintained source branch and the fork's default branch.
- `maintenance/` on `custom-main`: active scripts and their docs.
- `statusline-maintenance`: retained historical branch. Its complete history
  was imported under `maintenance/`; it is no longer an active worktree.
- The fork's original `main` is retained. It is not the custom release branch.
- Both maintained branches block force pushes and deletion on GitHub.
- Use normal commits and fast-forward pushes to the user's fork. Do not rebase,
  reset, force-push, or use GitHub **Sync fork** on `custom-main`.
- Read `.statusline-upstream.json` for the exact upstream tag, commit, and version.
  Do not assume that the version in these notes is still current.
- First tested source tag: `statusline-tested-0.166.0`. Backup branches also keep
  the original feature commits. Promotion adds a `statusline-before-*` tag.
- Keep binaries, credentials, personal configs, caches, and receipts out of Git.
- Commit and push source, maintenance scripts, and related notes together on
  `custom-main`. The research repository stores only the independent reference
  snapshot. Do not register it as a submodule or worktree.

## Important failure already fixed

The first prototype used the development workspace version `0.0.0`. The UI
tests passed, but `/model` used a catalog that omitted `gpt-6.1-sol`, and a saved
ChatGPT login could not use that model. The package version affects model
catalog requests, headers, cache validity, and automatic credential storage.

The fix was to base the feature on the exact official `rust-v0.166.0` release,
retain its real workspace version, regenerate internal workspace lockfile
versions, and rebuild. Both model catalogs then matched. Native `/model`
selection and one ephemeral `gpt-6.1-sol` request returning `OK` passed.

Never fix this by changing only the displayed version or one HTTP header. Do
not delete login files, log out, or remove model caches as a routine repair.

The optional `openai-api-credit-promo` MCP endpoint also returned HTTP 403 with
`cf-mitigated: challenge` on November 3, 2026. The supported per-server policy
`plugins."openai-developers@openai-curated-remote".mcp_servers."openai-api-credit-promo".enabled`
is now false in the base user config. This skips the blocked credit-offer
connection and preserves the rest of the plugin. Fresh native startup and
`/mcp` confirmed the warning was gone, the promo server disabled, and local
API-key confirmation connected. Read `notes.md` for the setting and recovery
instructions. Do not remove this policy as a routine cleanup, edit cached
plugin manifests, or treat this endpoint failure as a model-login failure.

## Build, test, and update

Read `STATUSLINE_FORK.md` and `maintenance/README.md` before an update.
`maintenance/AGENTS.md` explains script changes and verification details.

Use an exact stable release tag. `update.py stage` merges it into a candidate
branch and worktree. Conflicts require inspection and a manual resolution in
the candidate; leave the working build in place. Regenerate the internal
workspace package versions in `Cargo.lock` for the selected release.

`update.py verify` runs the focused Rust tests and builds the CLI. It requires
a complete matching official package, copies its helper programs and resources,
then replaces only its CLI with the custom build. Its receipt pins the candidate
commit and all package files and modes. Check the printed candidate command,
then promote after the user accepts it. Promotion pushes the release tag,
backup tag, and a fast-forward branch update before switching the trial binary.
Rollback changes the selected executable package and keeps Git history.

The known working toolchain is `+1.97.1`; the release requested `1.95.0`.
The build cache is `/tmp/codex-multiline-target`. Recheck the upstream toolchain
on later releases. Do not change the official release version to a custom name.

Relevant Rust filters include `status_line`, `status_surface::tests`,
`multi_select_picker::tests`, `bottom_pane::footer::tests`, and
`footer_state::tests`. The last filter covers the warning geometry regression.
Snapshot files contain intentional cell padding; exclude `*.snap` from
`git diff --check`. Keep nested module `AGENTS.md` instructions in scope.

The model UI smoke test uses a disposable trusted profile and private tmux
server. It checks explicit rows at different terminal sizes, `/statusline`
save/cancel, and native `/model` selection. It protects real configs byte for
byte and sends no inference prompt. Human typing cadence and a stable Ready
state are needed; instant command pastes can trigger the composer's paste logic.

The runtime verifier removes API credential overrides only in its child
environment so it can use the saved ChatGPT login. Do not print or copy keys or
tokens. Inference is a separate optional check, not a default update test.

Do not rerun Rust tests or rebuild for documentation-only or launcher-only
changes. Verify the changed behavior. A later promotion still needs a receipt
for its exact candidate commit. The running package can precede docs-only
source commits; read the installation state instead of guessing from HEAD.

## Packaging and pending work

The CLI resolves helpers beside its canonical executable. Keep matching
`codex-code-mode-host` and package resources with every custom CLI. Copy them
out of the official updater cache; a symlink into an official release can break
when that release is pruned. Do not edit `standalone/current` or official package
contents. Do not delete current or previous custom packages referenced in state.

Legacy one-shot editing scripts and the old forced-cwd trial launcher remain
under `file.scripts.d`. They are not the maintained update entry point. Do not
reapply old source replacement scripts to a new release.

The user requested research on official contribution requirements after local
acceptance. That report was paused for the model failure. No upstream issue,
PR, or comment has been published. Check current official requirements before
reporting, and get explicit authorization before publishing anything.
