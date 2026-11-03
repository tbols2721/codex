#!/usr/bin/env python3
"""Check explicit rows and native /model selection in a scratch profile.

Use --run only after the trial binary has been rebuilt. This test sends no
natural-language prompt and makes no model inference request. The application
can fetch its model catalog during startup and while opening /model.
The real named profile is protected byte-for-byte and is never copied or edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
import uuid


CHECKOUT: Path
BINARY: Path
CONFIG_DIRECTORY = Path.home() / ".codex"
TRIAL_PROFILE: Path
BASE_CONFIG = CONFIG_DIRECTORY / "config.toml"
CAPTURE: Path
EXPECTED_VERSION: str
INITIAL_MODEL = "gpt-6-astra"
INITIAL_EFFORT = "medium"
TARGET_MODEL = "gpt-6.1-sol"
TARGET_EFFORT = "medium"
ROW_ITEMS = [
    "model-with-reasoning", "run-state",
    "line-break", "codex-version", "profile",
    "line-break", "reasoning", "current-dir",
]


def fixture_profile() -> bytes:
    """Use stable populated fields without depending on the user's current rows."""
    return f'''# Disposable maintenance-gate fixture; this file belongs to one smoke run.
check_for_update_on_startup = false
model = "{INITIAL_MODEL}"
model_reasoning_effort = "{INITIAL_EFFORT}"

[tui]
fullscreen_transcript = true
alternate_screen = "always"
animations = false
status_line = {json.dumps(ROW_ITEMS)}
status_line_use_colors = false

[tui.keymap.composer]
submit = "enter"

[tui.keymap.list]
move_up = "up"
move_down = "down"
move_left = "left"
move_right = "right"
jump_top = "home"
accept = "enter"
cancel = "esc"

[projects.{json.dumps(str(CHECKOUT))}]
trust_level = "trusted"
'''.encode("utf-8")


class SmokeFailure(RuntimeError):
    """The smoke test did not meet a required condition."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


class Driver:
    def __init__(self, profile_name: str, protected: dict[Path, bytes], log, startup_timeout: float):
        self.profile_name = profile_name
        self.profile_path = CONFIG_DIRECTORY / f"{profile_name}.config.toml"
        self.protected = protected
        self.log = log
        self.startup_timeout = startup_timeout
        self.socket = f"codex-statusline-model-ui-{uuid.uuid4().hex}"
        self.session = "model-smoke"
        self.pane = f"{self.session}:0.0"
        self.prefix = ["tmux", "-L", self.socket, "-f", "/dev/null"]
        self.environment = os.environ.copy()
        self.environment.pop("TMUX", None)
        for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            self.environment.pop(variable, None)
        self.environment["TERM"] = "xterm-256color"
        self.server_attempted = False
        self.overall_deadline = time.monotonic() + startup_timeout + 100

    def note(self, message: str) -> None:
        self.log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}] {message}\n")
        self.log.flush()
        print(message, flush=True)

    def guard(self) -> None:
        for path, original in self.protected.items():
            if path.read_bytes() != original:
                raise SmokeFailure(f"Protected config changed: {path}. This test will not restore or edit it.")
        if time.monotonic() >= self.overall_deadline:
            raise SmokeFailure("The overall smoke-test deadline expired.")

    def tmux(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            self.prefix + list(arguments),
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if check and result.returncode:
            raise SmokeFailure(f"tmux {' '.join(arguments)} failed: {result.stderr.strip()}")
        return result

    def screen(self, label: str | None = None) -> str:
        screen = self.tmux("capture-pane", "-p", "-t", self.pane).stdout
        if label:
            self.note(f"SCREEN: {label}")
            self.log.write(screen + "\n")
            self.log.flush()
        return screen

    def wait(self, label: str, predicate, timeout: float = 15) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.guard()
            screen = self.screen()
            if predicate(screen):
                return self.screen(label)
            if "Trust this folder?" in screen:
                self.screen("unexpected trust prompt")
                raise SmokeFailure("A trust prompt appeared. No trust action was sent, to preserve config bytes.")
            if "Update now" in screen or "Update available" in screen:
                self.screen("unexpected update prompt")
                raise SmokeFailure("An update prompt appeared. No update action was sent.")
            dead = self.tmux("display-message", "-p", "-t", self.pane, "#{pane_dead}").stdout.strip()
            if dead == "1":
                self.screen("application exited")
                raise SmokeFailure(f"The application exited while waiting for {label}.")
            time.sleep(0.2)
        self.screen(f"timeout: {label}")
        raise SmokeFailure(f"Timed out after {timeout:g} seconds waiting for {label}.")

    def footer_index(self, screen: str, model: str, *, require_ready: bool = True) -> int | None:
        if any(title in screen for title in ("Select Model", "Select Reasoning Level", "Configure Status Line")):
            return None
        for index, line in reversed(list(enumerate(screen.splitlines()))):
            if normalized(model) in normalized(line) and (
                not require_ready or re.search(r"\bReady\b", line)
            ):
                return index
        return None

    def wait_stable_ready(self, label: str, model: str, timeout: float = 15) -> str:
        ready_since = None

        def stable(screen: str) -> bool:
            nonlocal ready_since
            if self.footer_index(screen, model) is None:
                ready_since = None
                return False
            now = time.monotonic()
            if ready_since is None:
                ready_since = now
            return now - ready_since >= 1.0

        return self.wait(label, stable, timeout=timeout)

    def start(self) -> None:
        self.guard()
        self.note(f"Private tmux server: {self.socket}; temporary profile: {self.profile_name}")
        self.server_attempted = True
        self.tmux(
            "new-session", "-d", "-s", self.session, "-x", "140", "-y", "40",
            "-c", str(CHECKOUT), "bash --noprofile --norc",
        )
        self.tmux("set-option", "-t", self.session, "status", "off")
        self.tmux("set-option", "-sg", "escape-time", "25")
        self.tmux("set-window-option", "-t", f"{self.session}:0", "remain-on-exit", "on")
        command = "exec " + shlex.join([
            str(BINARY), "--no-daemon", "--profile", self.profile_name, "--cd", str(CHECKOUT),
        ])
        self.tmux("send-keys", "-t", self.pane, "-l", "--", command)
        self.tmux("send-keys", "-t", self.pane, "Enter")
        self.wait_stable_ready(
            "startup footer with fixture model",
            INITIAL_MODEL,
            timeout=self.startup_timeout,
        )

    def check_three_rows(self, model: str, effort: str, label: str) -> None:
        screen = self.screen(label)
        index = self.footer_index(screen, model)
        if index is None:
            raise SmokeFailure("The expected model footer is missing.")
        rows = screen.splitlines()[index:index + 3]
        if len(rows) != 3 or effort not in rows[0].lower():
            raise SmokeFailure("Row 1 does not show the expected model and reasoning level.")
        if not rows[1].strip().startswith(EXPECTED_VERSION):
            raise SmokeFailure("The release version did not remain on assigned row 2.")
        if not rows[2].strip().lower().startswith(effort):
            raise SmokeFailure("The independent reasoning field did not remain on assigned row 3.")
        if any(normalized(model) in normalized(row) for row in rows[1:]):
            raise SmokeFailure("The model field moved to another status row.")
        trailing = [line for line in screen.splitlines()[index + 3:] if line.strip()]
        if len(trailing) > 1:
            raise SmokeFailure("Extra status rows appeared below the three configured rows.")
        self.saved_rows()
        self.note("Model, release version, and reasoning remain on their three assigned rows.")

    def resize_and_check(self, width: int, height: int, model: str, effort: str) -> None:
        self.tmux("resize-window", "-t", f"{self.session}:0", "-x", str(width), "-y", str(height))
        self.wait_stable_ready(f"Ready at {width}x{height}", model)
        self.check_three_rows(model, effort, f"three assigned rows at {width}x{height}")

    def open_command(self, command: str, title: str, model: str) -> None:
        self.guard()
        self.wait_stable_ready(f"stable Ready before typing {command}", model)
        # Match a human key cadence so the composer does not interpret this as a paste.
        for character in command:
            self.guard()
            self.tmux("send-keys", "-t", self.pane, "-l", "--", character)
            time.sleep(0.05)
        time.sleep(0.4)
        screen = self.screen(f"{command} typed before Enter")
        if re.search(rf"^\s*›\s*{re.escape(command)}\s*$", screen, re.MULTILINE) is None:
            raise SmokeFailure(f"The composer does not contain exactly {command}. No Enter was sent.")
        self.tmux("send-keys", "-t", self.pane, "Enter")
        self.wait(title, lambda screen: title in screen)

    def open_model_picker(self) -> None:
        self.open_command("/model", "Select Model", INITIAL_MODEL)

    def saved_rows(self) -> None:
        saved = tomllib.loads(self.profile_path.read_text(encoding="utf-8"))
        if saved.get("tui", {}).get("status_line") != ROW_ITEMS:
            raise SmokeFailure("The scratch profile's explicit row choices changed.")

    def check_status_line_picker(self) -> None:
        for confirm in (False, True):
            self.open_command("/statusline", "Configure Status Line", INITIAL_MODEL)
            self.tmux("send-keys", "-t", self.pane, "-l", "--", "start")
            self.wait(
                "two enabled break markers and an available disabled marker",
                lambda screen: "Configure Status Line" in screen
                and len(re.findall(r"\[x\]\s+Start next line", screen)) == 2
                and re.search(r"\[ \]\s+Start next line", screen) is not None,
            )
            self.tmux("send-keys", "-t", self.pane, "Enter" if confirm else "Escape")
            self.wait_stable_ready("Ready after row save" if confirm else "Ready after row cancel", INITIAL_MODEL)
            self.saved_rows()
        self.check_three_rows(INITIAL_MODEL, INITIAL_EFFORT, "three rows survive picker cancel and save")

    def choose_numbered(self, title: str, label, description: str) -> None:
        self.guard()
        screen = self.screen()
        if title not in screen:
            raise SmokeFailure(f"Refused to select {description} outside {title}.")
        matches = []
        for line in screen.splitlines():
            match = re.match(r"^\s*(?:›\s*)?([1-9])\.\s+(.*)$", line)
            if match and label(match.group(2)):
                matches.append(match.group(1))
        if len(matches) != 1:
            self.screen(f"missing or ambiguous numbered choice: {description}")
            raise SmokeFailure(f"Expected one numbered choice for {description}; found {len(matches)}.")
        self.screen(f"before selecting {description}")
        # Nonsearchable native pickers accept their displayed numeric shortcut
        # directly (list_selection_view.rs::select_shortcut).
        self.tmux("send-keys", "-t", self.pane, "-l", "--", matches[0])
        time.sleep(0.3)

    def choose_model(self) -> None:
        screen = self.screen()
        if "Select Model and Effort" not in screen and "All models" in screen:
            self.choose_numbered("Select Model", lambda label: label.startswith("All models"), "All models")
            self.wait("all-models picker", lambda screen: "Select Model and Effort" in screen)
        screen = self.screen()
        if normalized(TARGET_MODEL) not in normalized(screen):
            if "Select Model" not in screen:
                raise SmokeFailure("Refused to navigate outside the model picker.")
            # The current model can scroll the first choice out of view. Home
            # is the native default list.jump_top binding in this copied profile.
            self.tmux("send-keys", "-t", self.pane, "Home")
            time.sleep(0.3)
        self.wait(
            "GPT-6.1 Sol is listed",
            lambda screen: "Select Model" in screen and normalized(TARGET_MODEL) in normalized(screen),
        )
        self.choose_numbered(
            "Select Model", lambda label: normalized(label).startswith(normalized(TARGET_MODEL)), TARGET_MODEL,
        )
        self.wait(
            "reasoning picker for GPT-6.1 Sol",
            lambda screen: "Select Reasoning Level for" in screen
            and normalized(TARGET_MODEL) in normalized(screen),
        )
        self.choose_numbered(
            "Select Reasoning Level for", lambda label: re.match(r"Medium(?:\s|\(|$)", label) is not None,
            "supported Medium reasoning",
        )
        self.wait(
            "footer after GPT-6.1 Sol selection",
            lambda screen: (index := self.footer_index(screen, TARGET_MODEL)) is not None
            and TARGET_EFFORT in screen.splitlines()[index].lower(),
        )
        self.wait(
            "temporary profile saved GPT-6.1 Sol with medium reasoning",
            lambda _screen: self.saved_selection(),
        )

    def saved_selection(self) -> bool:
        saved = tomllib.loads(self.profile_path.read_text(encoding="utf-8"))
        if saved.get("model") != TARGET_MODEL or saved.get("model_reasoning_effort") != TARGET_EFFORT:
            return False
        self.saved_rows()
        return True

    def cleanup(self) -> None:
        if self.server_attempted:
            result = self.tmux("kill-server", check=False)
            if result.returncode and not any(
                text in result.stderr for text in ["no server running", "No such file or directory"]
            ):
                raise SmokeFailure(f"Could not stop the private tmux server: {result.stderr.strip()}")
            self.server_attempted = False


def main() -> int:
    global CHECKOUT, BINARY, TRIAL_PROFILE, CAPTURE, EXPECTED_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True, help="candidate source worktree")
    parser.add_argument("--binary", type=Path, required=True, help="candidate executable staged outside the worktree")
    parser.add_argument("--expected-version", required=True, help="release version required from the candidate executable")
    parser.add_argument("--profile", default="statusline-trial", help="existing real profile to protect; this test uses a separate fixture")
    parser.add_argument("--run", action="store_true", help="run only after the binary has been rebuilt")
    parser.add_argument("--startup-timeout", type=float, default=45, help="startup deadline in seconds, 5 to 90")
    args = parser.parse_args()
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.expected_version) is None:
        parser.error("--expected-version must be a release version such as 0.166.0")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.profile) is None:
        parser.error("--profile must be a plain profile name")
    CHECKOUT = args.checkout.expanduser().resolve()
    BINARY = args.binary.expanduser().resolve()
    if BINARY.is_relative_to(CHECKOUT):
        parser.error("--binary must be staged outside the candidate worktree")
    EXPECTED_VERSION = args.expected_version
    TRIAL_PROFILE = CONFIG_DIRECTORY / f"{args.profile}.config.toml"
    CAPTURE = Path("/tmp") / f"codex-statusline-model-ui-{EXPECTED_VERSION}-{uuid.uuid4().hex[:12]}.txt"
    fixture = fixture_profile()
    tomllib.loads(fixture.decode("utf-8"))
    if not 5 <= args.startup_timeout <= 90:
        parser.error("--startup-timeout must be between 5 and 90 seconds")
    if not args.run:
        print("Plan only. After the binary is rebuilt, use --run.")
        print("Create a deterministic scratch profile with three explicit rows.")
        print("Check 120x32 and 80x24 layouts, then /statusline cancel and unchanged save.")
        print("Open /model, select GPT-6.1 Sol and Medium, then check the footer and temporary saved profile.")
        print(f"Capture screens to {CAPTURE}; hash-check the real trial and base config files.")
        print("No inference prompt. Remove only the private tmux server and temporary profile.")
        return 0

    if shutil.which("tmux") is None:
        raise SmokeFailure("tmux is not installed.")
    if not CHECKOUT.is_dir() or not BINARY.is_file() or not os.access(BINARY, os.X_OK):
        raise SmokeFailure("The candidate worktree and staged executable must be prepared first.")
    if os.environ.get("CODEX_HOME") and Path(os.environ["CODEX_HOME"]).resolve() != CONFIG_DIRECTORY:
        raise SmokeFailure("CODEX_HOME points elsewhere. This test will not change it.")
    protected = {path: path.read_bytes() for path in [TRIAL_PROFILE, BASE_CONFIG]}
    version = subprocess.run([str(BINARY), "--version"], capture_output=True, text=True, timeout=10, check=True)
    match = re.search(r"\b\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version.stdout)
    if match is None or match.group(0) != EXPECTED_VERSION:
        raise SmokeFailure(f"Expected rebuilt binary {EXPECTED_VERSION}; got {version.stdout.strip()}.")
    profile_name = f"statusline-model-ui-{os.getpid()}-{uuid.uuid4().hex[:12]}"
    temporary_profile = CONFIG_DIRECTORY / f"{profile_name}.config.toml"
    profile_created = False
    driver = None
    result = 0
    with CAPTURE.open("w", encoding="utf-8") as log:
        try:
            # Exclusive creation ensures this run owns the only profile it can remove.
            descriptor = os.open(temporary_profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            profile_created = True
            with os.fdopen(descriptor, "wb") as profile:
                profile.write(fixture)
            driver = Driver(profile_name, protected, log, args.startup_timeout)
            for path, original in protected.items():
                driver.note(f"Protected SHA-256 before: {path.name} {digest(original)}")
            driver.note(f"Binary version: {version.stdout.strip()}; deterministic fixture rows: 3")
            driver.start()
            driver.check_three_rows(INITIAL_MODEL, INITIAL_EFFORT, "initial three-row fixture")
            driver.resize_and_check(120, 32, INITIAL_MODEL, INITIAL_EFFORT)
            driver.resize_and_check(80, 24, INITIAL_MODEL, INITIAL_EFFORT)
            driver.resize_and_check(140, 40, INITIAL_MODEL, INITIAL_EFFORT)
            driver.check_status_line_picker()
            driver.open_model_picker()
            driver.choose_model()
            driver.check_three_rows(TARGET_MODEL, TARGET_EFFORT, "three rows after native model selection")
            driver.resize_and_check(80, 24, TARGET_MODEL, TARGET_EFFORT)
            driver.screen("final footer; no inference prompt submitted")
            driver.note(f"Temporary saved model: {TARGET_MODEL}; reasoning: {TARGET_EFFORT}")
        except KeyboardInterrupt:
            result = 130
            if driver:
                driver.note("Interrupted; cleaning only this test's resources.")
        except Exception as error:
            result = 1
            log.write(f"FAIL: {error}\n")
            print(f"FAIL: {error}", file=sys.stderr)
            if driver:
                try:
                    driver.screen("failure")
                except Exception:
                    pass
        finally:
            if driver:
                try:
                    driver.cleanup()
                except Exception as error:
                    result = 1
                    log.write(f"Cleanup failed: {error}\n")
            if profile_created:
                try:
                    temporary_profile.unlink()
                except FileNotFoundError:
                    pass
                except Exception as error:
                    result = 1
                    log.write(f"Temporary profile cleanup failed: {error}\n")
            for path, original in protected.items():
                try:
                    current = path.read_bytes()
                    log.write(f"Protected SHA-256 after: {path.name} {digest(current)}\n")
                    if current != original:
                        result = 1
                        log.write(f"FAIL: Protected config bytes changed: {path}\n")
                except Exception as error:
                    result = 1
                    log.write(f"Protected config check failed: {path}: {error}\n")
            log.write(f"{'PASS' if result == 0 else 'FAIL'}\n")
            log.flush()
    print(f"{'PASS' if result == 0 else 'FAIL'}. Screen record: {CAPTURE}")
    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.SubprocessError, SmokeFailure, tomllib.TOMLDecodeError) as error:
        print(f"Smoke test could not start: {error}", file=sys.stderr)
        sys.exit(1)
