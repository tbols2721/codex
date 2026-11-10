#!/usr/bin/env python3
"""Install regular command files and independent copies of the maintenance tools."""

from pathlib import Path
import os
import shutil
import tempfile


def main():
    source = Path(__file__).resolve().parent
    installed = Path.home() / ".local/share/codex-statusline"
    scripts = installed / "maintenance"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ["codexJoe.py", "update.py", "verify_codex_statusline_runtime.py",
                 "smoke_test_codex_statusline_model.py"]:
        shutil.copy2(source / name, scripts / name)
    shutil.copy2(source.parent / "STATUSLINE_FORK.md", installed / "STATUSLINE_FORK.md")
    commands = Path.home() / ".local/bin"
    commands.mkdir(parents=True, exist_ok=True)
    for name, script in [("codexJoe", "codexJoe.py"), ("codex-statusline-update", "update.py")]:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=commands)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write("#!/bin/sh\n"
                             f'exec /usr/bin/python3 "$HOME/.local/share/codex-statusline/maintenance/{script}" "$@"\n')
            os.chmod(temporary, 0o755)
            os.replace(temporary, commands / name)
        finally:
            Path(temporary).unlink(missing_ok=True)
    print(f"Installed regular commands in {commands}; maintenance copies are in {scripts}.")


if __name__ == "__main__":
    main()
