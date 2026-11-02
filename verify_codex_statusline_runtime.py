#!/usr/bin/env python3
"""Compare the installed and rebuilt trial runtimes; optionally verify one model turn.

Default: compare versions and model catalogs using the saved ChatGPT login.
--inference: also submit one ephemeral read-only trial turn that must return OK.
No config or login repair is performed. Raw catalogs and credentials are not printed.
The candidate binary must be staged outside its source checkout.
"""

from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile


CHECKOUT: Path
CODEX_DIRECTORY = Path.home() / ".codex"
OFFICIAL: Path
TRIAL: Path
BASE_CONFIG = CODEX_DIRECTORY / "config.toml"
TRIAL_PROFILE: Path
PROFILE_NAME: str
AUTH_FILE = CODEX_DIRECTORY / "auth.json"
LOCK_FILE = Path("/tmp/codex-statusline-runtime-verification.lock")
MODEL = "gpt-6.1-sol"
PROMPT = "Reply with exactly OK. Do not use tools."
EXPECTED_VERSION: str
CREDENTIAL_OVERRIDES = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
CHILD_ENVIRONMENT = os.environ.copy()
for variable in CREDENTIAL_OVERRIDES:
    CHILD_ENVIRONMENT.pop(variable, None)


class VerificationFailure(RuntimeError):
    """A required runtime check did not pass."""


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_error_tags(text: str) -> list[str]:
    lowered = text.casefold()
    markers = {
        "authentication": (
            "authentication failed", "invalid_api_key", "401 unauthorized",
            "403 forbidden", "refresh token failed", "not logged in",
        ),
        "model": (
            "model_not_found", "model is not supported",
            "not supported when using codex with a chatgpt account",
        ),
        "network": ("error sending request", "connection refused", "timed out"),
        "arguments": ("unexpected argument", "unrecognized subcommand", "invalid value"),
    }
    return [tag for tag, values in markers.items() if any(value in lowered for value in values)]


def run_command(arguments: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        arguments,
        cwd=CHECKOUT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=CHILD_ENVIRONMENT,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        # Stop only the process group created by this invocation.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        if isinstance(error, KeyboardInterrupt):
            raise
        raise VerificationFailure(f"A bounded CLI check exceeded {timeout:g} seconds.") from None
    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def require_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode:
        tags = safe_error_tags(result.stderr + "\n" + result.stdout)
        detail = ", ".join(tags) if tags else "diagnostic text withheld"
        raise VerificationFailure(f"{label} exited {result.returncode}: {detail}.")


def check_saved_login() -> None:
    configured_home = os.environ.get("CODEX_HOME")
    if configured_home and Path(configured_home).resolve() != CODEX_DIRECTORY:
        raise VerificationFailure("CODEX_HOME selects a different login location.")
    # The agent's shell can have API credentials. Omit those overrides only in
    # child processes so this check uses the user's existing ChatGPT login.
    auth = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    if auth.get("auth_mode") != "chatgpt":
        raise VerificationFailure("The installed saved login is not in ChatGPT mode.")
    # Do not print, copy, modify, or refresh credentials directly.
    del auth


def read_version(binary: Path) -> str:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise VerificationFailure(f"The required executable is not ready: {binary}")
    result = run_command([str(binary), "--version"], timeout=10)
    require_success(result, "version check")
    match = re.fullmatch(r"codex-cli\s+(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*", result.stdout.strip())
    if match is None:
        raise VerificationFailure("The CLI did not return the expected version format.")
    return match.group(1)


def read_catalog(binary: Path, label: str) -> list[dict]:
    # Source uses OnlineIfUncached here. A valid shared cache may satisfy the request.
    # --profile is intentionally absent: debug models rejects that runtime option.
    result = run_command([str(binary), "debug", "models"], timeout=45)
    require_success(result, f"{label} model catalog")
    if any(tag in {"authentication", "model"} for tag in safe_error_tags(result.stderr)):
        raise VerificationFailure(f"{label} reported an authentication or model error during catalog loading.")
    catalog = json.loads(result.stdout)
    if not isinstance(catalog, dict):
        raise VerificationFailure(f"{label} returned an invalid model-catalog document.")
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        raise VerificationFailure(f"{label} returned an empty or invalid model catalog.")
    safe_models = []
    for model in models:
        slug = model.get("slug")
        if not isinstance(slug, str) or re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", slug) is None:
            raise VerificationFailure(f"{label} returned an invalid model identifier.")
        safe_models.append({
            "slug": slug,
            "visibility": model.get("visibility"),
            "supported_in_api": model.get("supported_in_api"),
            "default_reasoning_level": model.get("default_reasoning_level"),
            "supported_reasoning_levels": [
                level.get("effort") for level in model.get("supported_reasoning_levels", [])
            ],
        })
    safe_models.sort(key=lambda model: model["slug"])
    selected = next((model for model in safe_models if model["slug"] == MODEL), None)
    if selected is None or selected["visibility"] != "list":
        raise VerificationFailure(f"{label} does not list {MODEL} in the active catalog.")
    print(json.dumps({"runtime": label, "model_count": len(safe_models), "models": safe_models}), flush=True)
    return safe_models


def verify_inference() -> None:
    help_result = run_command([str(TRIAL), "exec", "--help"], timeout=10)
    require_success(help_result, "trial exec help")
    required_flags = (
        "--ephemeral", "--profile", "--model", "--sandbox",
        "--json", "--color", "--output-last-message",
    )
    if any(flag not in help_result.stdout for flag in required_flags):
        raise VerificationFailure("The rebuilt exec CLI does not advertise the verified flags.")

    descriptor, answer_name = tempfile.mkstemp(prefix="codex-statusline-runtime-answer-", suffix=".txt", dir="/tmp")
    os.close(descriptor)
    answer_path = Path(answer_name)
    print(f"One ephemeral trial turn will write its final answer to {answer_path}", flush=True)
    arguments = [
        str(TRIAL), "exec",
        "--ephemeral",
        "--profile", PROFILE_NAME,
        "--model", MODEL,
        "--sandbox", "read-only",
        "--config", 'model_reasoning_effort="low"',
        "--cd", str(CHECKOUT),
        "--json",
        "--color", "never",
        "--output-last-message", str(answer_path),
        PROMPT,
    ]
    # Exactly one exec invocation. This driver never retries inference.
    result = run_command(arguments, timeout=90)
    require_success(result, "trial inference")
    counts = Counter()
    item_types = set()
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise VerificationFailure("The exec event stream contained non-JSON output.") from None
        event_type = event.get("type")
        counts[event_type] += 1
        if event_type in {"error", "turn.failed"}:
            raise VerificationFailure(f"The exec stream reported {event_type}; diagnostic content withheld.")
        if event_type in {"item.started", "item.updated", "item.completed"}:
            item_type = event.get("item", {}).get("type")
            item_types.add(item_type)
            if item_type not in {"agent_message", "reasoning"}:
                raise VerificationFailure(f"The no-tool turn emitted an unexpected item type: {item_type!r}.")
    if counts["turn.started"] != 1 or counts["turn.completed"] != 1:
        raise VerificationFailure("The exec stream did not contain exactly one successful turn.")
    if answer_path.read_text(encoding="utf-8").strip() != "OK":
        raise VerificationFailure(f"The final answer was not exactly OK. Review {answer_path}.")
    # Optional MCP startup can report access failures while the requested model turn succeeds.
    # The exit code and exec error events above govern failure of the model request.
    startup_warnings = Counter()
    for line in result.stderr.splitlines():
        lowered = line.casefold()
        if re.search(r"\bmcp\b|\brmcp\b|codex_mcp|codex_rmcp", lowered) and any(
            marker in lowered for marker in ("warn", "error", "fail", "403", "forbidden")
        ):
            startup_warnings["optional_mcp_startup"] += 1
        elif "403" in lowered or "forbidden" in lowered:
            startup_warnings["startup_access_message"] += 1
    print(json.dumps({"startup_warning_categories": dict(startup_warnings)}), flush=True)
    print(json.dumps({
        "inference": "passed", "model": MODEL, "reasoning_effort": "low",
        "completed_turns": counts["turn.completed"], "tool_items": 0,
        "final_answer": "OK", "answer_file": str(answer_path),
    }), flush=True)


def main() -> int:
    global CHECKOUT, OFFICIAL, TRIAL, TRIAL_PROFILE, PROFILE_NAME, EXPECTED_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True, help="candidate source worktree")
    parser.add_argument("--binary", type=Path, required=True, help="candidate executable staged outside the worktree")
    parser.add_argument("--official", type=Path, required=True, help="matching official release executable")
    parser.add_argument("--expected-version", required=True, help="release version required from both executables")
    parser.add_argument("--profile", default="statusline-trial", help="existing user profile to protect; also used by optional inference")
    parser.add_argument("--inference", action="store_true", help="also run the single authorized read-only OK turn")
    args = parser.parse_args()
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.expected_version) is None:
        parser.error("--expected-version must be a release version such as 0.166.0")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.profile) is None:
        parser.error("--profile must be a plain profile name")
    CHECKOUT = args.checkout.expanduser().resolve(strict=True)
    if not CHECKOUT.is_dir():
        parser.error("--checkout must name a source worktree directory")
    TRIAL = args.binary.expanduser().resolve(strict=True)
    if TRIAL.is_relative_to(CHECKOUT):
        parser.error("--binary must be staged outside the candidate worktree")
    OFFICIAL = args.official.expanduser().resolve(strict=True)
    EXPECTED_VERSION = args.expected_version
    PROFILE_NAME = args.profile
    TRIAL_PROFILE = CODEX_DIRECTORY / f"{PROFILE_NAME}.config.toml"
    with LOCK_FILE.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VerificationFailure("Another runtime-verification driver is already running.") from None
        before = {path: fingerprint(path) for path in (BASE_CONFIG, TRIAL_PROFILE)}
        try:
            check_saved_login()
            versions = {"official": read_version(OFFICIAL), "trial": read_version(TRIAL)}
            print(json.dumps({"versions": versions}), flush=True)
            if versions["official"] != EXPECTED_VERSION or versions["trial"] != versions["official"]:
                raise VerificationFailure(f"Both runtimes must report {EXPECTED_VERSION} before catalog or inference checks.")
            official_models = read_catalog(OFFICIAL, "official")
            trial_models = read_catalog(TRIAL, "trial")
            if official_models != trial_models:
                raise VerificationFailure("The installed and trial model slugs or support fields differ.")
            print(f"Active catalogs match and list {MODEL}.", flush=True)
            if args.inference:
                verify_inference()
            else:
                print("Inference skipped. Use --inference for the single authorized OK turn.", flush=True)
        finally:
            changed = [str(path) for path, digest in before.items() if fingerprint(path) != digest]
            if changed:
                raise VerificationFailure(f"Config files changed during verification; no user edits were overwritten: {changed!r}")
            print("Base config and all trial profile edits remain byte-for-byte unchanged.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Runtime verification interrupted; no inference retry was made.", file=sys.stderr)
        sys.exit(130)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, VerificationFailure) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
