"""Small, permission-friendly tools used by the repository Agent CLI."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Dict


def run_command(command: list[str], cwd: str = ".", timeout: int = 120) -> Dict:
    """Run a fixed test command without invoking a shell."""
    try:
        executable = shutil.which(command[0])
        if not executable:
            return {"command": command, "returncode": 127, "output": f"未找到命令: {command[0]}", "timed_out": False}
        result = subprocess.run(
            [executable, *command[1:]],
            cwd=str(Path(cwd).resolve()),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "output": result.stdout,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "output": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "timed_out": True,
        }
    except OSError as exc:
        return {"command": command, "returncode": 127, "output": str(exc), "timed_out": False}


def find_test_commands(root: str = ".") -> list[list[str]]:
    """Suggest conservative test commands from common project files."""
    path = Path(root).resolve()
    commands = []
    if (path / "pyproject.toml").exists() or (path / "pytest.ini").exists():
        commands.append(["python", "-m", "pytest"])
    elif (path / "setup.py").exists():
        commands.append(["python", "-m", "pytest"])
    if (path / "package.json").exists():
        commands.append(["npm", "test"])
    return commands
