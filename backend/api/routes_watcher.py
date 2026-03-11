"""Watcher endpoints (manage watched paths)."""

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.api.routes_files import (
    _sync_watcher_to_inclusion_directories,
    load_file_indexing_config,
    save_file_indexing_config,
)
from backend.schemas import SyncPathsRequest, WatchPathRequest, WatchPathResponse

# Assuming the app is run from root, we can import watcher
try:
    from watcher.core.database import FileRegistry
except ImportError:
    # Fallback for when running backend isolation without watcher pkg
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    from watcher.core.database import FileRegistry
router = APIRouter(prefix="/watcher", tags=["watcher"])

# Use project root for DB so all code (watcher API + file-indexing sync) uses the same file
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = str(_PROJECT_ROOT / "file_registry.db")
registry = FileRegistry(db_path=DB_PATH)


def get_user_root_paths():
    """
    Return the most root paths for the current user on this system (home, documents).
    Use these as defaults so the app is not tied to the project folder.
    """
    home = os.path.abspath(os.path.expanduser("~"))
    docs = os.path.join(home, "Documents")
    if not os.path.isdir(docs):
        docs = home
    return {"user_root": home, "documents": docs if os.path.isdir(docs) else home}


@router.get("/user-root")
async def get_user_root():
    """Return the suggested root path for this user's system (home dir, documents)."""
    return get_user_root_paths()


def open_folder_dialog():
    """Open native folder picker via subprocess so tkinter runs on a real main thread (required on macOS)."""
    script = _PROJECT_ROOT / "scripts" / "folder_picker.py"
    if not script.exists():
        raise HTTPException(
            status_code=503,
            detail="Folder picker script not found. Enter the folder path manually.",
        )
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Folder picker failed: {e}. Enter the folder path manually.",
        ) from e

    if result.returncode != 0:
        if "TKINTER_UNAVAILABLE" in (result.stderr or ""):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Folder picker not available: this Python was not built with tkinter. "
                    "See docs/TKINTER_SETUP.md or enter the folder path manually."
                ),
            )
        raise HTTPException(
            status_code=503,
            detail=result.stderr
            or "Folder picker failed. Enter the folder path manually.",
        )

    path = (result.stdout or "").strip()
    return path if path else ""


def open_file_dialog():
    """Open native file picker via subprocess so tkinter runs on a real main thread (required on macOS)."""
    script = _PROJECT_ROOT / "scripts" / "file_picker.py"
    if not script.exists():
        raise HTTPException(
            status_code=503,
            detail="File picker script not found. Enter file paths manually.",
        )
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"File picker failed: {e}. Enter file paths manually.",
        ) from e

    if result.returncode != 0:
        if "TKINTER_UNAVAILABLE" in (result.stderr or ""):
            raise HTTPException(
                status_code=503,
                detail=(
                    "File picker not available: this Python was not built with tkinter. "
                    "See docs/TKINTER_SETUP.md or enter file paths manually."
                ),
            )
        raise HTTPException(
            status_code=503,
            detail=result.stderr or "File picker failed. Enter file paths manually.",
        )

    lines = [
        line.strip()
        for line in (result.stdout or "").strip().splitlines()
        if line.strip()
    ]
    return lines


@router.post("/pick-files")
def pick_files():
    """Open native file picker and return the selected file paths only (no persistence)."""
    paths = open_file_dialog()
    if not paths:
        return {"paths": [], "status": "cancelled"}

    clean_paths = []
    for p in paths:
        clean = os.path.abspath(os.path.expanduser(p)).rstrip(os.sep)
        if os.path.exists(clean):
            clean_paths.append(clean)

    if not clean_paths:
        return {"paths": [], "status": "error", "detail": "No valid files selected"}

    return {"paths": clean_paths, "status": "selected"}


@router.post("/pick-folder")
def pick_folder():
    """Open native folder picker and return the selected path only (no persistence).

    The caller is responsible for adding the path to local state and
    persisting via the file-indexing save endpoint.
    """
    path = open_folder_dialog()
    if not path or not path.strip():
        return {"path": "", "status": "cancelled"}

    clean_path = os.path.abspath(os.path.expanduser(path)).rstrip(os.sep)
    if not os.path.exists(clean_path):
        return {"path": clean_path, "status": "error", "detail": "Path does not exist"}

    return {"path": clean_path, "status": "selected"}


@router.post("/browse")
def browse_folder(type: str = Query("inclusion", description="inclusion or exclusion")):
    """Open native folder picker (tkinter); get full path and add to inclusion or exclusion in YAML."""
    path = open_folder_dialog()
    if not path or not path.strip():
        return {"path": "", "status": "cancelled"}

    clean_path = os.path.abspath(os.path.expanduser(path)).rstrip(os.sep)
    if not os.path.exists(clean_path):
        return {"path": clean_path, "status": "error", "detail": "Path does not exist"}

    config = load_file_indexing_config()

    if type == "exclusion":
        # Add full path to exclusion directories only (no watcher)
        exclusion = config.setdefault(
            "exclusion", {"files": [], "directories": [], "patterns": []}
        )
        dirs = list(exclusion.get("directories", []))
        normalized = {os.path.abspath(p).rstrip(os.sep) for p in dirs}
        if clean_path not in normalized:
            dirs.append(clean_path)
            exclusion["directories"] = dirs
            config["exclusion"] = exclusion
            save_file_indexing_config(config)
        return {"path": clean_path, "status": "added", "type": "exclusion"}
    else:
        # inclusion (default): add to watcher and YAML inclusion
        registry.add_watch_path(clean_path, [])
        inclusion = config.setdefault("inclusion", {"files": [], "directories": []})
        dirs = list(inclusion.get("directories", []))
        normalized = {os.path.abspath(p).rstrip(os.sep) for p in dirs}
        if clean_path not in normalized:
            dirs.append(clean_path)
            inclusion["directories"] = dirs
            config["inclusion"] = inclusion
            save_file_indexing_config(config)
            _sync_watcher_to_inclusion_directories(dirs)
        updated_paths = registry.get_watch_paths()
        return {
            "path": clean_path,
            "status": "added",
            "type": "inclusion",
            "active_paths": updated_paths,
        }


@router.post("/path", response_model=WatchPathResponse)
async def add_watch_path(req: WatchPathRequest):
    # Normalize the main path (no trailing sep) so GET and sync use the same key
    raw = os.path.abspath(os.path.expanduser(req.path or ""))
    clean_path = raw.rstrip(os.sep) if raw else raw

    if not clean_path or not os.path.exists(clean_path):
        raise HTTPException(
            status_code=400, detail=f"Path does not exist: {clean_path}"
        )

    # Normalize excluded files
    clean_excluded = []
    if req.excluded_files:
        clean_excluded = [
            os.path.abspath(os.path.expanduser(f)) for f in req.excluded_files
        ]

    registry.add_watch_path(clean_path, clean_excluded)

    # Persist to YAML inclusion so the path survives POST /watcher/sync and appears in the UI
    config = load_file_indexing_config()
    inclusion = config.setdefault("inclusion", {"files": [], "directories": []})
    dirs = list(inclusion.get("directories", []))
    normalized = {os.path.abspath(os.path.expanduser(p)).rstrip(os.sep) for p in dirs}
    if clean_path not in normalized:
        dirs.append(clean_path)
        inclusion["directories"] = dirs
        config["inclusion"] = inclusion
        save_file_indexing_config(config)

    updated_paths = registry.get_watch_paths()
    return {"status": "added", "active_paths": updated_paths}


@router.get("/path")
async def get_watch_paths():
    paths = registry.get_watch_paths()
    # Normalize path keys for consistent responses
    for p in paths:
        if p.get("path"):
            p["path"] = p["path"].rstrip(os.sep)
    return {"active_paths": paths}


@router.delete("/path", response_model=WatchPathResponse)
async def remove_watch_path_by_path(
    path: str = Query(..., description="Path to stop watching")
):
    """Remove a path from the watcher (sets is_active=0). Uses query param so DELETE works reliably."""
    raw = os.path.abspath(os.path.expanduser(path))
    clean_path = raw.rstrip(os.sep) if raw else raw
    registry.remove_watch_path(clean_path)
    # Remove from YAML inclusion so it does not reappear after refresh or next sync
    config = load_file_indexing_config()
    inclusion = config.get("inclusion") or {}
    dirs = list(inclusion.get("directories", []))
    normalized_dirs = [
        os.path.abspath(os.path.expanduser(p)).rstrip(os.sep) for p in dirs
    ]
    if clean_path in normalized_dirs:
        dirs = [p for p, n in zip(dirs, normalized_dirs) if n != clean_path]
        inclusion["directories"] = dirs
        config["inclusion"] = inclusion
        save_file_indexing_config(config)
    return {"status": "removed", "active_paths": registry.get_watch_paths()}


@router.post("/sync", response_model=WatchPathResponse)
async def sync_watch_paths(req: SyncPathsRequest):
    """
    Sync monitor_config with the inclusion list from the UI (YAML stores full paths).
    - Any path in monitor_config that is NOT in req.paths (normalized) gets is_active=0.
    - Any path in req.paths gets added/updated with is_active=1.
    All paths are normalized (abspath, no trailing sep) for comparison.
    """
    raw = [p.strip() for p in (req.paths or []) if p and p.strip()]
    inclusion_set = {os.path.abspath(os.path.expanduser(p)).rstrip(os.sep) for p in raw}
    all_db_paths = registry.get_all_monitor_paths()
    for db_path in all_db_paths:
        normalized_db = db_path.rstrip(os.sep)
        if normalized_db not in inclusion_set:
            registry.remove_watch_path(db_path)
    for p in raw:
        full_path = os.path.abspath(os.path.expanduser(p))
        registry.add_watch_path(full_path, [])
    return {"status": "synced", "active_paths": registry.get_watch_paths()}
