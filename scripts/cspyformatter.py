"""Unified Python formatter: runs isort, Black, and ruff in one command.

Usage:
    uv run python scripts/cspyformatter.py [paths...]       # format specific files/dirs (isort/black/ruff)
    uv run python scripts/cspyformatter.py                   # format entire project
    uv run python scripts/cspyformatter.py --check           # check-only mode (CI: isort/black/ruff)
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def _find_tool(name: str) -> str:
    """Locate a dev tool next to the running Python interpreter, then fall back to PATH.

    This ensures the venv-installed binaries are found even when the venv is not
    activated (e.g. ``python scripts/cspyformatter.py``).

    Args:
        name: Executable name (e.g. "black").

    Returns:
        Resolved path string to the executable.

    Raises:
        SystemExit: If the tool cannot be found anywhere.
    """
    venv_bin = Path(sys.executable).parent / name
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which(name)
    if found:
        return found
    print(f"ERROR: '{name}' not found. Install dev deps: uv sync --group dev")
    sys.exit(1)


# Steps run in order: isort (imports) → black (formatting) → ruff (lint)
STEPS = [
    {
        "name": "isort",
        "format": [_find_tool("isort"), "--profile", "black"],
        "check": [_find_tool("isort"), "--profile", "black", "--check-only", "--diff"],
    },
    {
        "name": "black",
        "format": [_find_tool("black")],
        "check": [_find_tool("black"), "--check", "--diff"],
    },
    {
        "name": "ruff",
        "format": [_find_tool("ruff"), "check", "--fix"],
        "check": [_find_tool("ruff"), "check"],
    },
]

DEFAULT_TARGETS = ["."]


def run(check_only: bool = False, targets: List[str] | None = None) -> int:
    """Execute all formatting steps sequentially.

    Args:
        check_only: If True, run in check/diff mode without modifying files.
        targets: File or directory paths to format. Defaults to project root.

    Returns:
        0 on success, 1 if any step fails.
    """
    targets = targets or DEFAULT_TARGETS
    failed: List[str] = []

    for step in STEPS:
        mode = "check" if check_only else "format"
        cmd = step[mode] + targets
        label = step["name"]
        print(f"\n{'='*50}")
        print(f"  Running {label} ({mode})...")
        print(f"  $ {' '.join(cmd)}")
        print(f"{'='*50}\n")

        result = subprocess.run(cmd)
        if result.returncode != 0:
            failed.append(label)
            # In format mode, keep going so all tools get a chance to fix things.
            # In check mode, continue to report all violations.

    print(f"\n{'='*50}")
    if failed:
        print(f"  FAILED steps: {', '.join(failed)}")
        print(f"{'='*50}")
        return 1

    print("  All checks passed ✓" if check_only else "  Formatting complete ✓")
    print(f"{'='*50}")
    return 0


def main() -> None:
    """Parse CLI arguments and run the formatter."""
    args = sys.argv[1:]
    check_only = "--check" in args
    targets = [a for a in args if a != "--check"] or None
    sys.exit(run(check_only=check_only, targets=targets))


if __name__ == "__main__":
    main()
