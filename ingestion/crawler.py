"""File crawler: recursive scan for supported document types."""

import fnmatch
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class DiscoveredFile:
    """A file discovered by the crawler."""

    path: Path
    file_name: str
    extension: str
    size_bytes: int
    modified_timestamp: float
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash and self.path.exists():
            self.content_hash = _file_hash(self.path)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _matches_exclude(path: Path, patterns: tuple[str, ...], root: Path) -> bool:
    try:
        rel_str = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel_str = str(path)
    for pat in patterns:
        if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(str(path), pat):
            return True
    return False


def crawl_directory(
    root: Path,
    *,
    supported_extensions: tuple[str, ...] = (
        ".pdf",
        ".txt",
        ".md",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".oga",
        ".opus",
        ".webm",
        ".aiff",
        ".aif",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
    ),
    exclude_patterns: tuple[str, ...] = (
        "**/node_modules/**",
        "**/.git/**",
        "**/__pycache__/**",
        "**/*.pyc",
    ),
    max_file_size_mb: float = 50.0,
) -> Iterator[DiscoveredFile]:
    """Recursively discover supported files in directory."""
    root = Path(root).resolve()
    ext_set = frozenset(supported_extensions)
    max_bytes = int(max_file_size_mb * 1024 * 1024)

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in ext_set:
            continue
        if _matches_exclude(path, exclude_patterns, root):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > max_bytes:
            continue
        yield DiscoveredFile(
            path=path,
            file_name=path.name,
            extension=path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_timestamp=stat.st_mtime,
        )
