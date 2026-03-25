"""File metadata endpoints."""

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.deps import get_context
from core.context import AppContext

try:
    from watcher.core.database import FileRegistry
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from watcher.core.database import FileRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# Path to file indexing config; project root is parent of config dir
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "file_indexing.yaml"
PROJECT_ROOT = CONFIG_PATH.parent.parent


def _to_full_path(path: str, base: Optional[Path] = None) -> str:
    """Convert a path to absolute. If path is relative, resolve against user home (not project folder)."""
    p = (path or "").strip()
    if not p:
        return p
    path_obj = Path(p)
    if path_obj.is_absolute():
        return str(path_obj.resolve())
    # Use user home as base for relative paths so uploads/imports don't end up inside the project
    if base is None:
        base = Path(os.path.expanduser("~"))
    return str((base / p).resolve())


def _paths_to_full_paths(paths: list, base: Optional[Path] = None) -> list:
    return [_to_full_path(x, base) for x in (paths or [])]


def _sync_watcher_to_inclusion(
    directories: List[str],
    files: List[str],
    scheduler: Optional[Any] = None,
) -> None:
    """Sync monitor_config and watched_files to match inclusion.directories + inclusion.files.

    When a path is removed from the inclusion list, also purge its data from
    local_search.db (files, chunks, vectors) so stale content is no longer
    returned during retrieval.

    When *scheduler* is provided (from AppContext), immediately enqueue indexing
    jobs for newly-added files so indexing starts without waiting for the
    background reconciliation loop.
    """
    db_path = PROJECT_ROOT / "file_registry.db"
    if not db_path.exists():
        return
    registry = FileRegistry(db_path=str(db_path))

    raw_dirs = [p.strip() for p in (directories or []) if p and p.strip()]
    raw_files = [p.strip() for p in (files or []) if p and p.strip()]

    dir_set = {os.path.abspath(os.path.expanduser(p)).rstrip(os.sep) for p in raw_dirs}
    file_set = {os.path.abspath(os.path.expanduser(p)) for p in raw_files}
    all_inclusion = dir_set | file_set

    # Collect paths being removed so we can purge from unified DB
    removed_paths: List[str] = []
    for existing in registry.get_all_monitor_paths():
        if existing.rstrip(os.sep) not in all_inclusion:
            removed_paths.append(existing)
            registry.remove_watch_path(existing)

    # Purge removed paths from local_search.db (files + chunks + vectors)
    if removed_paths:
        try:
            from db.unified import UnifiedDatabase

            unified_db_path = str(PROJECT_ROOT / "local_search.db")
            unified_db = UnifiedDatabase(db_path=unified_db_path)
            for rp in removed_paths:
                norm = rp.rstrip(os.sep)
                if os.path.isdir(norm) or not os.path.exists(norm):
                    unified_db.remove_files_under_directory(norm)
                else:
                    unified_db.remove_file(norm)
        except Exception as exc:
            logger.warning("Failed to purge removed paths from unified DB: %s", exc)

    # Track which monitor_config paths are still ACTIVE after removals.
    # New paths (not in this set) will have indexing jobs scheduled immediately.
    # Use get_watch_paths() (active only) so that re-added paths (previously
    # deactivated) are correctly identified as new and scheduled for indexing.
    existing_paths = {d["path"].rstrip(os.sep) for d in registry.get_watch_paths()}

    # Ensure directories are active in monitor_config and schedule indexing
    from ingestion.pipeline import PipelineConfig

    sup_exts = set(PipelineConfig().supported_extensions)

    for p in raw_dirs:
        full_path = os.path.abspath(os.path.expanduser(p))
        registry.add_watch_path(full_path, [])
        # If this directory is newly added, immediately schedule its files
        if scheduler and full_path.rstrip(os.sep) not in existing_paths:
            _schedule_directory(full_path, registry, scheduler, sup_exts)

    # Ensure individual files are active in monitor_config AND watched_files
    for p in raw_files:
        full_path = os.path.abspath(os.path.expanduser(p))
        path_obj = Path(full_path)
        if path_obj.is_file():
            registry.add_watch_path(full_path, [])
            registry.upsert_file(full_path, path_obj.stat().st_mtime)
            # Immediately schedule indexing for newly-added files
            if scheduler and full_path not in existing_paths:
                ext = path_obj.suffix.lower()
                if ext in sup_exts:
                    try:
                        scheduler.schedule(full_path, source="ui")
                        logger.info("Scheduled indexing for file: %s", full_path)
                    except Exception as exc:
                        logger.warning("Failed to schedule %s: %s", full_path, exc)


def _schedule_directory(
    dir_path: str,
    registry: FileRegistry,
    scheduler: Any,
    supported_extensions: Set[str],
) -> None:
    """Walk a directory and schedule an indexing job for each supported file."""
    for root, _dirs, filenames in os.walk(dir_path):
        for name in filenames:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in supported_extensions:
                continue
            fp = os.path.join(root, name)
            try:
                registry.upsert_file(fp, os.stat(fp).st_mtime)
                scheduler.schedule(fp, source="ui")
            except Exception as exc:
                logger.warning("Failed to schedule %s: %s", fp, exc)


def _sync_watcher_to_inclusion_directories(directories: List[str]) -> None:
    """Backwards-compatible wrapper — syncs directories and reads files from YAML.

    Reads ``inclusion.files`` from the persisted config so that individual
    files are not accidentally deactivated when only directories are passed.
    """
    config = load_file_indexing_config()
    inclusion = config.get("inclusion", {})
    files = inclusion.get("files", []) or []
    _sync_watcher_to_inclusion(directories, files)


def load_file_indexing_config() -> Dict[str, Any]:
    """Load file indexing configuration from YAML."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading file indexing config: {e}")
    return {
        "inclusion": {"files": [], "directories": []},
        "exclusion": {"files": [], "directories": [], "patterns": []},
        "context": {"files": []},
    }


def save_file_indexing_config(config: Dict[str, Any]) -> None:
    """Save file indexing configuration to YAML."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


class FileIndexingUpdate(BaseModel):
    inclusion: Optional[Dict[str, List[str]]] = None
    exclusion: Optional[Dict[str, List[str]]] = None
    context: Optional[Dict[str, List[str]]] = None


def _is_excluded(
    abs_path: str,
    name: str,
    is_dir: bool,
    excluded_dirs: Set[str],
    excluded_files: Set[str],
    exclusion_patterns: List[str],
) -> bool:
    """Check if a path should be excluded based on exclusion config."""
    normalized = abs_path.rstrip(os.sep)
    # Check explicit directory exclusion
    if is_dir and normalized in excluded_dirs:
        return True
    # Check if path is under an excluded directory
    for excl_dir in excluded_dirs:
        if normalized.startswith(excl_dir + os.sep):
            return True
    # Check explicit file exclusion
    if not is_dir and normalized in excluded_files:
        return True
    # Check exclusion patterns (glob-style matching against the file/folder name)
    for pattern in exclusion_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        # Also match directory patterns like "node_modules/" against directory names
        if (
            is_dir
            and pattern.endswith("/")
            and fnmatch.fnmatch(name, pattern.rstrip("/"))
        ):
            return True
    return False


def build_file_tree(
    path: str,
    base_path: str = "",
    excluded_dirs: Optional[Set[str]] = None,
    excluded_files: Optional[Set[str]] = None,
    exclusion_patterns: Optional[List[str]] = None,
    file_statuses: Optional[Dict[str, str]] = None,
    supported_extensions: Optional[Set[str]] = None,
) -> list:
    """Recursively build file tree structure with absolute paths, filtering exclusions.

    Each file node receives a ``status`` field:
    - ``indexed``  – file has been successfully embedded and is searchable.
    - ``pending``  – file is queued / being indexed.
    - ``unsupported`` – file extension is not handled by the ingestion pipeline.
    """
    full_path = Path(path)
    if not full_path.exists():
        return []

    excl_dirs = excluded_dirs or set()
    excl_files = excluded_files or set()
    excl_patterns = exclusion_patterns or []
    statuses = file_statuses or {}
    sup_exts = supported_extensions or set()

    nodes = []
    try:
        for item in sorted(full_path.iterdir()):
            if item.name.startswith("."):
                continue

            abs_path = str(item.resolve())
            is_dir = item.is_dir()

            # Skip excluded items
            if _is_excluded(
                abs_path, item.name, is_dir, excl_dirs, excl_files, excl_patterns
            ):
                continue

            node: Dict[str, Any] = {
                "id": abs_path.replace(os.sep, "_"),
                "name": item.name,
                "type": "folder" if is_dir else "file",
                "path": abs_path,
            }

            if is_dir:
                children = build_file_tree(
                    str(item),
                    base_path or str(full_path),
                    excl_dirs,
                    excl_files,
                    excl_patterns,
                    statuses,
                    sup_exts,
                )
                if children:
                    node["children"] = children
            else:
                # Determine file status for the UI
                ext = item.suffix.lower()
                if sup_exts and ext not in sup_exts:
                    node["status"] = "unsupported"
                elif abs_path in statuses:
                    node["status"] = statuses[abs_path]
                else:
                    node["status"] = "pending"

            nodes.append(node)
    except PermissionError:
        pass

    return nodes


@router.get("/")
async def list_files():
    """List available files in a tree structure built from inclusion directories and files."""
    config = load_file_indexing_config()
    inclusion = config.get("inclusion", {})
    inclusion_dirs = inclusion.get("directories", []) or []
    inclusion_files = inclusion.get("files", []) or []

    if not inclusion_dirs and not inclusion_files:
        return {"files": []}

    # Build exclusion sets from config
    exclusion_cfg = config.get("exclusion", {})
    excluded_dirs: Set[str] = {
        os.path.abspath(os.path.expanduser(p)).rstrip(os.sep)
        for p in (exclusion_cfg.get("directories", []) or [])
        if p and p.strip()
    }
    excluded_files: Set[str] = {
        os.path.abspath(os.path.expanduser(p)).rstrip(os.sep)
        for p in (exclusion_cfg.get("files", []) or [])
        if p and p.strip()
    }
    exclusion_patterns: List[str] = exclusion_cfg.get("patterns", []) or []

    # Load file statuses from the unified DB and supported extensions
    file_statuses: Dict[str, str] = {}
    try:
        from db.unified import UnifiedDatabase

        unified_db_path = str(PROJECT_ROOT / "local_search.db")
        unified_db = UnifiedDatabase(db_path=unified_db_path)
        file_statuses = unified_db.get_all_file_statuses()
    except Exception:
        pass

    from ingestion.pipeline import PipelineConfig

    supported_extensions: Set[str] = set(PipelineConfig().supported_extensions)

    all_nodes = []

    # Directory trees
    for dir_path in inclusion_dirs:
        if not dir_path or not Path(dir_path).exists():
            continue
        tree = build_file_tree(
            dir_path,
            dir_path,
            excluded_dirs,
            excluded_files,
            exclusion_patterns,
            file_statuses,
            supported_extensions,
        )
        if tree:
            resolved = str(Path(dir_path).resolve())
            dir_name = Path(dir_path).name
            root_node = {
                "id": resolved.replace(os.sep, "_"),
                "name": dir_name,
                "type": "folder",
                "path": resolved,
                "children": tree,
            }
            all_nodes.append(root_node)

    # Individual files — add as top-level file nodes (skip if excluded or non-existent)
    for file_path in inclusion_files:
        if not file_path or not file_path.strip():
            continue
        abs_path = os.path.abspath(os.path.expanduser(file_path)).rstrip(os.sep)
        p = Path(abs_path)
        if not p.exists() or not p.is_file():
            continue
        if _is_excluded(
            abs_path, p.name, False, excluded_dirs, excluded_files, exclusion_patterns
        ):
            continue

        ext = p.suffix.lower()
        if supported_extensions and ext not in supported_extensions:
            status = "unsupported"
        elif abs_path in file_statuses:
            status = file_statuses[abs_path]
        else:
            status = "pending"

        all_nodes.append(
            {
                "id": abs_path.replace(os.sep, "_"),
                "name": p.name,
                "type": "file",
                "path": abs_path,
                "status": status,
            }
        )

    return {"files": all_nodes}


@router.get("/indexing")
async def get_file_indexing_config():
    """Get current file indexing configuration."""
    return load_file_indexing_config()


@router.post("/indexing")
async def update_file_indexing_config(
    update: FileIndexingUpdate,
    ctx: AppContext = Depends(get_context),
):
    """Update file indexing configuration."""
    config = load_file_indexing_config()

    if update.inclusion is not None:
        inclusion_data = {
            "files": _paths_to_full_paths(update.inclusion.get("files", [])),
            "directories": _paths_to_full_paths(
                update.inclusion.get("directories", [])
            ),
        }
        config["inclusion"] = inclusion_data

    if update.exclusion is not None:
        exclusion_data = {
            "files": _paths_to_full_paths(update.exclusion.get("files", [])),
            "directories": _paths_to_full_paths(
                update.exclusion.get("directories", [])
            ),
            "patterns": update.exclusion.get("patterns", []),
        }
        config["exclusion"] = exclusion_data

    if update.context is not None:
        context_files = update.context.get("files", [])
        filtered_files = [f for f in context_files if not f.endswith("/")]
        config["context"] = {"files": _paths_to_full_paths(filtered_files)}

    save_file_indexing_config(config)
    # Sync monitor_config (and watched_files for individual files) with the saved inclusion list.
    # Pass the scheduler so new files are enqueued for indexing immediately.
    inclusion = config.get("inclusion", {})
    _sync_watcher_to_inclusion(
        inclusion.get("directories", []),
        inclusion.get("files", []),
        scheduler=getattr(ctx, "scheduler", None),
    )
    return {"status": "ok", "config": config}


@router.get("/context")
async def get_context_files():
    """Get files selected for context (only leaf files, not directories)."""
    config = load_file_indexing_config()
    context_files = config.get("context", {}).get("files", [])
    # Filter out directories - only return actual files
    # Directories typically end with '/' or have no file extension
    # For now, we'll filter anything ending with '/'
    filtered = []
    for f in context_files:
        if not f.endswith("/"):
            # Also check if it's a real file path (has extension or is a known file)
            path_obj = Path(f)
            if path_obj.suffix or not path_obj.exists() or path_obj.is_file():
                filtered.append(f)
    return {"files": filtered}
