"""Parse checks for code and config files before indexing.

Validated (when possible):
  - .py          — ``ast.parse``
  - .json        — ``json.loads``
  - .toml        — ``tomllib.loads``
  - .yaml/.yml   — ``yaml.safe_load`` (requires PyYAML)
  - .ini/.cfg    — :class:`configparser.ConfigParser` (strict)
  - .css         — ``tinycss2`` parse (not .scss/.less; those are not plain CSS)
  - .js/.mjs/.cjs — ``node --check`` when ``node`` is on PATH (not .jsx; JSX is not valid JS)
  - .sh/.bash    — ``bash -n`` when ``bash`` is on PATH

Skipped (no reliable stdlib / no extra heavy toolchains):
  - .ts, .tsx, .jsx, .vue, .svelte, .scss, .less, .html, .sql, and most compiled languages
    (.java, .go, .rs, …) unless you add dedicated linters later.
"""

from __future__ import annotations

import ast
import json
import logging
import shutil
import subprocess
import tomllib
from configparser import ConfigParser, ParsingError
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CodeSyntaxError(Exception):
    """Raised when a file fails a syntax / parse check."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _normalize_ext(ext: str) -> str:
    e = ext.strip().lower()
    return e if e.startswith(".") else f".{e}"


def validate_code_syntax(ext: str, content: str, path: Optional[Path] = None) -> None:
    """Raise :class:`CodeSyntaxError` if *content* fails a check for *ext*.

    Unknown or intentionally skipped extensions are no-ops.
    """
    suffix = _normalize_ext(ext)

    if suffix == ".py":
        try:
            ast.parse(content, filename=str(path) if path else "<string>")
        except SyntaxError as e:
            raise CodeSyntaxError(
                f"Python syntax error (line {e.lineno or '?'}): {e.msg}"
            ) from e

    elif suffix == ".json":
        text = content.lstrip("\ufeff")
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            raise CodeSyntaxError(
                f"JSON parse error (line {e.lineno}, col {e.colno}): {e.msg}"
            ) from e

    elif suffix == ".toml":
        try:
            tomllib.loads(content)
        except tomllib.TOMLDecodeError as e:
            raise CodeSyntaxError(f"TOML parse error: {e}") from e

    elif suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.debug(
                "PyYAML not installed; skipping YAML syntax check for %s", path
            )
            return
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:  # type: ignore[attr-defined]
            raise CodeSyntaxError(f"YAML parse error: {e}") from e

    elif suffix in (".ini", ".cfg"):
        parser = ConfigParser(strict=True)
        try:
            parser.read_string(content)
        except ParsingError as e:
            raise CodeSyntaxError(f"INI/config parse error: {e}") from e

    elif suffix == ".css":
        try:
            import tinycss2
        except ImportError:
            logger.debug(
                "tinycss2 not installed; skipping CSS syntax check for %s", path
            )
            return
        rules = tinycss2.parse_stylesheet(
            content, skip_whitespace=True, skip_comments=True
        )
        for item in rules:
            if item.type == "error":
                msg = getattr(item, "message", None) or "invalid CSS"
                raise CodeSyntaxError(f"CSS parse error: {msg}")

    elif suffix in (".js", ".mjs", ".cjs"):
        node = shutil.which("node")
        if not node:
            logger.debug(
                "node not found; skipping JavaScript syntax check for %s", path
            )
            return
        if not path or not path.is_file():
            logger.debug("No file path; skipping node --check for stream source")
            return
        try:
            proc = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CodeSyntaxError(f"JavaScript check failed: {e}") from e
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or "syntax error"
            raise CodeSyntaxError(f"JavaScript syntax error: {err[:800]}")

    elif suffix in (".sh", ".bash"):
        bash = shutil.which("bash")
        if not bash:
            logger.debug("bash not found; skipping shell syntax check for %s", path)
            return
        if not path or not path.is_file():
            return
        try:
            proc = subprocess.run(
                [bash, "-n", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CodeSyntaxError(f"Shell syntax check failed: {e}") from e
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or "syntax error"
            raise CodeSyntaxError(f"Shell syntax error: {err[:800]}")
