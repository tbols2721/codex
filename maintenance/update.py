#!/usr/bin/env python3
"""Stage, verify, and promote release updates for the personal Codex fork.

No command replaces ~/.local/bin/codex or edits personal configuration.
Git conflicts are left in the candidate worktree for manual resolution.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import uuid

SCRIPTS = Path(__file__).resolve().parent
METADATA = ".statusline-upstream.json"
BRANCH = "custom-main"
TAG_PATTERN = re.compile(r"rust-v(\d+\.\d+\.\d+)")


class Stop(RuntimeError):
    pass


def run(*arguments, cwd=None, capture=False, check=True, **kwargs):
    result = subprocess.run(
        [str(argument) for argument in arguments], cwd=cwd, text=True,
        capture_output=capture, check=False, **kwargs,
    )
    if check and result.returncode:
        if capture and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        raise Stop(f"Command failed ({result.returncode}): {arguments[0]}")
    return result.stdout.strip() if capture else result


def git(checkout, *arguments, **kwargs):
    return run("git", "-C", checkout, *arguments, **kwargs)


def clean(checkout):
    if git(checkout, "status", "--porcelain", capture=True):
        raise Stop(f"Commit or set aside changes in {checkout} first. No files were discarded.")


def commit(checkout):
    return git(checkout, "rev-parse", "HEAD", capture=True)


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def point_link(path, target):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def package_files(package):
    return {str(path.relative_to(package)): {"sha256": fingerprint(path), "mode": stat.S_IMODE(path.stat().st_mode)}
            for path in sorted(Path(package).rglob("*")) if path.is_file()}


def recover_switch(args):
    journal = args.state / "pending-switch.json"
    if not journal.exists():
        return
    pending = json.loads(journal.read_text())
    launcher = args.source / "bin/codex-statusline"
    selected = str(launcher.resolve()) if launcher.exists() else None
    if selected == pending["new_target"]:
        state = pending["new_state"]
    elif selected in (pending["old_actual"], pending["old_restore"]):
        state = pending["old_state"]
        if pending["old_restore"] and selected != pending["old_restore"]:
            point_link(launcher, pending["old_restore"])
    else:
        raise Stop("An interrupted switch and the trial launcher disagree. Review pending-switch.json first.")
    write_json(args.state / "installation.json", state)
    journal.unlink()
    print("Recovered the installation record from an interrupted switch.")


def switch_package(args, old_state, new_state, old_restore):
    """Journal the selection and restore it if the state write fails.

    A process stop between atomic operations leaves the journal for recovery
    on the next invocation. Both executable packages remain intact.
    """
    launcher = args.source / "bin/codex-statusline"
    binary = Path(new_state["current"]) / "bin/codex"
    journal = args.state / "pending-switch.json"
    pending = {"old_actual": str(launcher.resolve()) if launcher.exists() else None,
               "old_restore": str(old_restore) if old_restore else None,
               "new_target": str(binary), "old_state": old_state, "new_state": new_state}
    write_json(journal, pending)
    try:
        point_link(launcher, binary)
        write_json(args.state / "installation.json", new_state)
    except BaseException:
        # A first adoption uses the byte-identical verified package as its old
        # restore target, so no regular executable needs to be overwritten back.
        try:
            if old_restore:
                point_link(launcher, old_restore)
            elif launcher.is_symlink() and launcher.resolve() == binary:
                launcher.unlink()
            write_json(args.state / "installation.json", old_state)
            journal.unlink()
        except BaseException:
            print("Switch recovery is recorded in pending-switch.json; rerun the update command.", file=sys.stderr)
        raise
    journal.unlink()


def metadata(checkout, pending_merge=False):
    data = json.loads((checkout / METADATA).read_text())
    match = TAG_PATTERN.fullmatch(data["tag"])
    if not match or data["version"] != match[1] or data["version"] == "0.0.0":
        raise Stop("The source metadata must select a stable, nonzero release version.")
    actual = git(checkout, "rev-parse", f"{data['tag']}^{{commit}}", capture=True)
    if actual != data["commit"]:
        raise Stop("The upstream tag and recorded upstream commit differ.")
    if pending_merge:
        if git(checkout, "rev-parse", "MERGE_HEAD^{commit}", capture=True) != actual:
            raise Stop("The pending merge does not match the recorded release.")
    else:
        git(checkout, "merge-base", "--is-ancestor", actual, "HEAD")
    workspace = tomllib.loads((checkout / "codex-rs/Cargo.toml").read_text())
    if workspace["workspace"]["package"]["version"] != data["version"]:
        raise Stop("The Cargo workspace version differs from the recorded release.")
    return data


def binary_version(binary):
    return run(binary, "--version", capture=True, timeout=15)


def current_branch(checkout):
    if git(checkout, "branch", "--show-current", capture=True) != BRANCH:
        raise Stop(f"The main checkout must be on {BRANCH}.")


def fetch_main(args):
    git(args.source, "fetch", "--quiet", "--no-tags", "origin",
        f"refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
    if commit(args.source) != git(args.source, "rev-parse", f"origin/{BRANCH}", capture=True):
        raise Stop("Local and remote custom-main differ. Review and reconcile them first.")


def stable_release(tag=None):
    endpoint = "repos/openai/codex/releases/" + (f"tags/{tag}" if tag else "latest")
    data = json.loads(run("gh", "api", endpoint, capture=True, timeout=45))
    if data.get("draft") or data.get("prerelease") or not TAG_PATTERN.fullmatch(data["tag_name"]):
        raise Stop("The selected GitHub release is not a stable Codex Rust release.")
    return data


def check(args):
    base = metadata(args.source)
    latest = stable_release()
    print(json.dumps({"branch": BRANCH, "current": base["tag"],
                      "latest": latest["tag_name"], "url": latest["html_url"]}, indent=2))


def stage(args):
    if not TAG_PATTERN.fullmatch(args.tag):
        raise Stop("Use an exact stable release tag, for example rust-v0.166.0.")
    clean(args.source)
    current_branch(args.source)
    fetch_main(args)
    old = metadata(args.source)
    if tuple(map(int, args.tag.removeprefix("rust-v").split("."))) <= tuple(map(int, old["version"].split("."))):
        raise Stop("Stage requires a newer release. The current branch was not changed.")
    stable_release(args.tag)
    git(args.source, "fetch", "--quiet", "--no-tags", "upstream",
        f"refs/tags/{args.tag}:refs/tags/{args.tag}")
    release_commit = git(args.source, "rev-parse", f"{args.tag}^{{commit}}", capture=True)
    version = args.tag.removeprefix("rust-v")
    candidate = args.updates / version
    candidate.parent.mkdir(parents=True, exist_ok=True)
    branch = f"update/statusline-{version}"
    run("git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", args.source, candidate)
    git(candidate, "remote", "set-url", "origin",
        git(args.source, "remote", "get-url", "origin", capture=True))
    git(candidate, "remote", "add", "upstream",
        git(args.source, "remote", "get-url", "upstream", capture=True))
    for key in ("user.name", "user.email"):
        value = git(args.source, "config", "--get", key, capture=True, check=False)
        if value:
            git(candidate, "config", key, value)
    git(candidate, "switch", "--quiet", "--no-track", "-c", branch, f"origin/{BRANCH}")
    print(f"Candidate: {candidate}", flush=True)
    merge = git(candidate, "merge", "--no-ff", "--no-commit", args.tag, check=False)
    if merge.returncode:
        print(f"Resolve the merge in {candidate}; the working build has not changed.", file=sys.stderr)
        print(f"After resolution, record tag {args.tag}, commit {release_commit}, and version {version} in {METADATA}.", file=sys.stderr)
        raise Stop("The candidate merge needs attention. No automatic conflict resolution was used.")
    new = {"schema": 1, "repository": "openai/codex", "tag": args.tag,
           "commit": release_commit, "version": version}
    write_json(candidate / METADATA, new)
    # Release tags can retain 0.0.0 entries for internal workspace packages.
    run("cargo", f"+{args.toolchain}", "update", "--workspace", "--offline", cwd=candidate / "codex-rs")
    metadata(candidate, pending_merge=True)
    git(candidate, "add", METADATA, "codex-rs/Cargo.lock")
    git(candidate, "commit", "-m", f"Merge OpenAI {args.tag} into the status-line fork")
    print(f"Next: {sys.executable} {__file__} verify {candidate} --official-package MATCHING_PACKAGE")


def receipt_path(args, checkout):
    return args.state / "verified" / f"{commit(checkout)}.json"


def verify(args):
    candidate = args.candidate.resolve()
    clean(candidate)
    base = metadata(candidate)
    git(candidate, "merge-base", "--is-ancestor", commit(args.source), "HEAD")
    head = commit(candidate)
    official = args.official_package.resolve()
    if binary_version(official / "bin/codex") != f"codex-cli {base['version']}":
        raise Stop("Use the official package that matches the candidate release version.")
    if not (official / "bin/codex-code-mode-host").is_file():
        raise Stop("The official package is missing its matching code-mode host.")
    cargo = ["cargo", f"+{args.toolchain}"]
    git(candidate, "diff", "--check", f"{base['commit']}..HEAD", "--", ".", ":(exclude)**/*.snap")
    for test_filter in ("status_line", "status_surface::tests", "multi_select_picker::tests", "bottom_pane::footer::tests", "footer_content::tests", "footer_state::tests"):
        run(*cargo, "test", "--quiet", "-p", "codex-tui", "--lib", test_filter,
            "--locked", "--target-dir", args.target, cwd=candidate / "codex-rs")
    run(*cargo, "build", "--quiet", "-p", "codex-cli", "--bin", "codex", "--locked",
        "--target-dir", args.target, cwd=candidate / "codex-rs")
    clean(candidate)
    if commit(candidate) != head:
        raise Stop("The candidate commit changed during verification.")
    package = args.packages / f"{base['version']}-{head[:12]}-{uuid.uuid4().hex[:8]}"
    package.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(official, package, symlinks=False)
    shutil.copy2(args.target / "debug/codex", package / "bin/codex")
    binary = package / "bin/codex"
    if binary_version(binary) != f"codex-cli {base['version']}":
        raise Stop("The built CLI does not report the selected release version.")
    shared = ["--checkout", str(candidate), "--binary", str(binary),
              "--expected-version", base["version"], "--profile", args.profile]
    run(sys.executable, SCRIPTS / "verify_codex_statusline_runtime.py", *shared,
        "--official", official / "bin/codex")
    run(sys.executable, SCRIPTS / "smoke_test_codex_statusline_model.py", "--run", *shared)
    clean(candidate)
    if commit(candidate) != head:
        raise Stop("The candidate commit changed during runtime verification.")
    proof = {"schema": 1, "commit": head, "tag": base["tag"], "package": str(package),
             "binary_sha256": fingerprint(binary), "package_files": package_files(package),
             "verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "checks": ["focused Rust tests", "CLI build", "version", "model catalog", "native model picker and rows"]}
    write_json(receipt_path(args, candidate), proof)
    print(f"Verified package: {package}")
    print(f"Try: {binary} --no-daemon --profile {args.profile}")
    print("After you accept it, run promote with this candidate checkout.")


def package_valid(package, digest, files):
    binary = Path(package) / "bin/codex"
    if not binary.is_file() or fingerprint(binary) != digest:
        raise Stop("The verified binary is missing or changed. Run verification again.")
    if not (Path(package) / "bin/codex-code-mode-host").is_file():
        raise Stop("The verified package has lost its code-mode helper.")
    for executable in (binary, Path(package) / "bin/codex-code-mode-host"):
        if not os.access(executable, os.X_OK):
            raise Stop(f"The package executable cannot run: {executable}")
    if package_files(Path(package)) != files:
        raise Stop("Package helpers, resources, or file modes changed. Run verification again.")
    return binary


def archive_existing(args, launcher):
    """Retain an unpackaged trial and its matching official helper/resources."""
    helper = args.source / "bin/codex-code-mode-host"
    if not helper.is_file():
        raise Stop("The existing trial has no usable code-mode helper; initialize its package first.")
    official = helper.resolve().parent.parent
    try:
        version = binary_version(launcher)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Stop("The existing trial executable cannot be checked for package preservation.") from error
    if (not re.fullmatch(r"codex-cli \d+\.\d+\.\d+", version) or version == "codex-cli 0.0.0"
            or not (official / "bin/codex").is_file()
            or binary_version(official / "bin/codex") != version):
        raise Stop("Cannot preserve the existing trial with a matching official package. Initialize it first.")
    package = args.packages / f"{version.split()[1]}-adopted-{uuid.uuid4().hex[:8]}"
    package.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(official, package, symlinks=False)
    shutil.copy2(launcher, package / "bin/codex")
    digest = fingerprint(launcher)
    files = package_files(package)
    package_valid(package, digest, files)
    return {"current": str(package), "current_sha256": digest, "current_files": files}


def promote(args):
    candidate = args.candidate.resolve()
    clean(args.source)
    clean(candidate)
    current_branch(args.source)
    fetch_main(args)
    base = metadata(candidate)
    proof = json.loads(receipt_path(args, candidate).read_text())
    if proof["commit"] != commit(candidate) or proof["tag"] != base["tag"]:
        raise Stop("The verification receipt does not match this candidate.")
    package = Path(proof["package"])
    binary = package_valid(package, proof["binary_sha256"], proof["package_files"])
    state_path = args.state / "installation.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    old_state = state.copy()
    old = state.get("current")
    launcher = args.source / "bin/codex-statusline"
    old_restore = None
    if old:
        old_binary = package_valid(old, state["current_sha256"], state["current_files"])
        old_restore = old_binary
        if launcher.resolve() != old_binary.resolve():
            raise Stop("The trial launcher differs from the recorded package. Review that change first.")
    elif launcher.exists():
        # Adopt the current tested build before a first update. Its bytes and
        # helper must match the verified package, so the old build is retained
        # in that package even when the original launcher is a regular file.
        legacy_helper = args.source / "bin/codex-code-mode-host"
        if (fingerprint(launcher) == proof["binary_sha256"] and legacy_helper.is_file()
                and fingerprint(legacy_helper) == fingerprint(package / "bin/codex-code-mode-host")):
            state["previous"] = str(package)
            state["previous_sha256"] = proof["binary_sha256"]
            state["previous_files"] = proof["package_files"]
            old_restore = binary
        else:
            state = archive_existing(args, launcher)
            old_state = state.copy()
            old = state["current"]
            old_restore = Path(old) / "bin/codex"
    git(args.source, "fetch", "--quiet", "--no-tags", candidate, commit(candidate))
    git(args.source, "merge-base", "--is-ancestor", "HEAD", commit(candidate))
    previous = commit(args.source)
    tag = f"statusline-before-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{previous[:12]}"
    git(args.source, "tag", "-a", tag, previous, "-m", f"Before promotion to {base['tag']}")
    git(args.source, "push", "--atomic", "origin", f"{commit(candidate)}:refs/heads/{BRANCH}",
        f"refs/tags/{tag}", f"refs/tags/{base['tag']}")
    git(args.source, "merge", "--ff-only", commit(candidate))
    if old and old != str(package):
        state["previous"] = old
        state["previous_sha256"] = state["current_sha256"]
        state["previous_files"] = state["current_files"]
    state["current"] = str(package)
    state["current_sha256"] = proof["binary_sha256"]
    state["current_files"] = proof["package_files"]
    # Only this fork's trial executable is switched. All package resources are
    # resolved beside its canonical binary, outside the official updater cache.
    switch_package(args, old_state, state, old_restore)
    print(f"Promoted {base['tag']} to {BRANCH}; backup source tag: {tag}")
    print(f"Trial executable: {args.source / 'bin/codex-statusline'}")


def rollback(args):
    path = args.state / "installation.json"
    state = json.loads(path.read_text())
    old_state = state.copy()
    if not state.get("previous"):
        raise Stop("No previous promoted package is recorded. Git backup tags remain available.")
    binary = package_valid(state["previous"], state["previous_sha256"], state["previous_files"])
    old_binary = package_valid(state["current"], state["current_sha256"], state["current_files"])
    if (args.source / "bin/codex-statusline").resolve() != old_binary.resolve():
        raise Stop("The trial launcher differs from the recorded current package.")
    state["current"], state["previous"] = state["previous"], state["current"]
    state["current_sha256"], state["previous_sha256"] = state["previous_sha256"], state["current_sha256"]
    state["current_files"], state["previous_files"] = state["previous_files"], state["current_files"]
    switch_package(args, old_state, state, old_binary)
    print(f"Trial executable rolled back to {binary}. Git history was retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=(SCRIPTS.parent if (SCRIPTS.parent / METADATA).is_file() else Path.home() / "Research/file.private-repos/codex-statusline"))
    parser.add_argument("--updates", type=Path, default=Path.home() / "Research/worktrees/codex-statusline")
    parser.add_argument("--state", type=Path, default=Path.home() / ".codex/statusline-maintenance")
    parser.add_argument("--packages", type=Path, default=Path.home() / ".local/lib/codex-statusline")
    parser.add_argument("--target", type=Path, default=Path("/tmp/codex-multiline-target"))
    parser.add_argument("--toolchain", default="1.97.1", help="installed Rust toolchain; update if a release requires it")
    parser.add_argument("--profile", default="statusline-trial", help="personal profile to protect during tests")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check").set_defaults(action=check)
    stage_parser = commands.add_parser("stage")
    stage_parser.add_argument("tag")
    stage_parser.set_defaults(action=stage)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("candidate", type=Path)
    verify_parser.add_argument("--official-package", type=Path, default=Path.home() / ".codex/packages/standalone/current")
    verify_parser.set_defaults(action=verify)
    promote_parser = commands.add_parser("promote")
    promote_parser.add_argument("candidate", type=Path)
    promote_parser.set_defaults(action=promote)
    commands.add_parser("rollback").set_defaults(action=rollback)
    args = parser.parse_args()
    for name in ("source", "updates", "state", "packages", "target"):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    args.state.mkdir(parents=True, exist_ok=True)
    try:
        with (args.state / "update.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop("Another update command is running.") from None
            recover_switch(args)
            args.action(args)
    except (Stop, OSError, KeyError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
