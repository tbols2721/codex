#!/usr/bin/env python3
"""Launch the promoted Codex fork with Joe's runtime profile and caller's cwd."""

import os
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parent
SOURCE = SCRIPTS.parent
BINARY = SOURCE / "bin/codex-statusline"
PROFILE = "statusline-trial"
GUIDE = SOURCE / "STATUSLINE_FORK.md"

# Match the root CLI and profile_v2_for_subcommand in the pinned release.
# Review these sets when the upstream CLI adds commands or root value options.
COMMANDS = {
    "agents", "tcp-tunnel", "exec", "e", "review", "login", "logout", "mcp",
    "plugin", "app-server", "remote-control", "app", "completion", "update",
    "doctor", "sandbox", "debug", "execpolicy", "apply", "a", "resume", "queue",
    "archive", "delete", "migrate-rollouts", "migrate-nfs-db", "unarchive", "fork",
    "cloud", "cloud-tasks", "exec-server", "features", "stdio-to-uds", "help",
}
RUNTIME_COMMANDS = {
    "agents", "exec", "e", "review", "resume", "queue", "archive", "delete",
    "unarchive", "fork", "mcp", "migrate-nfs-db", "sandbox",
}
VALUE_OPTIONS = {
    "--config", "--enable", "--disable", "--remote", "--remote-auth-token-env",
    "--image", "--model", "--local-provider", "--profile", "--sandbox", "--cd",
    "--add-dir", "--ask-for-approval", "--permissions-profile",
}
SHORT_VALUE_OPTIONS = {"c", "i", "m", "p", "s", "C", "a"}


def first_positional(arguments, index=0):
    """Find a positional token without treating an option value as a command."""
    while index < len(arguments):
        item = arguments[index]
        if item == "--":
            return None, None
        if item in VALUE_OPTIONS:
            index += 2
        elif item.startswith("--") or item == "-":
            if item == "-":
                return None, None
            index += 1
        elif item.startswith("-"):
            # A short option with an attached value consumes no following token.
            index += 2 if len(item) == 2 and item[1] in SHORT_VALUE_OPTIONS else 1
        else:
            return item, index
    return None, None


def root_command(arguments):
    command, position = first_positional(arguments)
    return (command, position) if command in COMMANDS else (None, None)


def launch_arguments(arguments):
    command, position = root_command(arguments)
    before_separator = arguments[:arguments.index("--")] if "--" in arguments else arguments
    if any(item in {"--help", "-h", "--version", "-V"} for item in before_separator):
        return list(arguments)
    runtime = command is None or command in RUNTIME_COMMANDS
    if command == "debug" and first_positional(arguments, position + 1)[0] == "prompt-input":
        runtime = True
    defaults = []
    explicit_profile = any(item in {"--profile", "-p"} or item.startswith("--profile=")
                           or item.startswith("-p") for item in before_separator)
    if runtime and not explicit_profile:
        defaults += ["--profile", PROFILE]
    remote = any(item == "--remote" or item.startswith("--remote=") for item in before_separator)
    if command in {None, "resume", "fork"} and not remote and "--no-daemon" not in before_separator:
        defaults += ["--no-daemon"]
    return defaults + list(arguments)


def main():
    arguments = sys.argv[1:]
    command, position = root_command(arguments)
    if command == "update" and not any(item in {"--help", "-h", "--version", "-V"} for item in arguments[:position]):
        tail = arguments[position + 1:]
        print(f"Custom updates use codex-statusline-update. Guide: {GUIDE}", flush=True)
        if tail in (["--help"], ["-h"]):
            print("codexJoe update checks releases. Stage, verify, and promote them with codex-statusline-update.")
            return 0
        if tail:
            print("codexJoe update accepts no arguments except --help.", file=sys.stderr)
            return 2
        os.execv(sys.executable, [sys.executable, str(SCRIPTS / "update.py"), "check"])
    if not BINARY.is_file() or not os.access(BINARY, os.X_OK):
        print(f"The promoted custom binary is unavailable: {BINARY}", file=sys.stderr)
        return 1
    # Do not chdir, replace CODEX_HOME, or change the caller's credential environment.
    os.execv(str(BINARY), [str(BINARY), *launch_arguments(arguments)])


if __name__ == "__main__":
    raise SystemExit(main())
