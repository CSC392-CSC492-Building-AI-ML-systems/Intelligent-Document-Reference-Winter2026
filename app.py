"""Main application entrypoint."""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FILE_INDEXING_DEFAULT_CONTENT = """# File indexing configuration
# This file is managed by the UI and defines which files are included/excluded

inclusion:
    # List of file paths to include in indexing
    files: []
    # List of directory paths to include (all files within)
    directories: []

exclusion:
    # List of file paths to exclude from indexing
    files: []
    # List of directory paths to exclude (all files within)
    directories: []
    # Exclusion patterns (wildcards, extensions, etc.)
    patterns: []

context:
    # List of file paths selected for current conversation context
    # Only leaf files (not directories) should be here
    files: []
"""


def _run_dev_mode(
    host: str = "127.0.0.1",
    port: int = 8000,
    with_electron: bool = False,
) -> None:
    """Run backend (uvicorn --reload) and frontend (npm run dev) for development."""
    project_root = Path(__file__).parent
    ui_dir = project_root / "ui"

    if not (ui_dir / "node_modules").exists():
        print("Node dependencies not found. Run: uv run app.py --setup")
        sys.exit(1)

    # Backend: uvicorn with --reload
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--reload",
        "--host",
        host,
        "--port",
        str(port),
    ]
    # Frontend: npm run dev, with API base URL so Vite proxies to backend
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE_URL"] = f"http://localhost:{port}"

    npm_path = shutil.which("npm")
    if not npm_path:
        print("ERROR: npm not found.")
        sys.exit(1)
    frontend_cmd = [npm_path, "run", "dev"]
    cwd_frontend = str(ui_dir)

    print("Starting development servers...")
    print(f"  Backend:  http://{host}:{port}")
    print(
        f"  Frontend: http://localhost:5173 (uses backend API at {frontend_env['VITE_API_BASE_URL']})"
    )
    if with_electron:
        print("  Electron: dev helper enabled")
    print("Press Ctrl+C to stop all dev processes.")

    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(project_root),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=cwd_frontend,
        env=frontend_env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    electron_proc = (
        _start_mini_mode_helper(host, port, ui_base_url="http://localhost:5173")
        if with_electron
        else None
    )

    def kill_both(*_args, **_kwargs):
        backend_proc.terminate()
        frontend_proc.terminate()
        if electron_proc and electron_proc.poll() is None:
            electron_proc.terminate()

    signal.signal(signal.SIGINT, kill_both)
    signal.signal(signal.SIGTERM, kill_both)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, kill_both)

    try:
        while (
            backend_proc.poll() is None
            and frontend_proc.poll() is None
            and (electron_proc is None or electron_proc.poll() is None)
        ):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    kill_both()
    backend_proc.wait()
    frontend_proc.wait()
    if electron_proc:
        try:
            electron_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            electron_proc.kill()


def _install_node_deps_if_missing(target_dir: Path, label: str) -> None:
    """Install npm dependencies in target_dir when node_modules is missing."""
    if (target_dir / "node_modules").exists():
        return

    npm_path = shutil.which("npm")
    if not npm_path:
        print("ERROR: npm not found.")
        sys.exit(1)

    print(f"{label} dependencies not found. Installing...")
    try:
        subprocess.run([npm_path, "install"], check=True, cwd=target_dir)
        print(f"✓ {label} dependencies installed")
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: failed to install {label} dependencies: {exc}")
        sys.exit(1)


def _ensure_electron_deps_ready(mini_mode_dir: Path) -> None:
    """Ensure Electron app dependencies are installed."""
    _install_node_deps_if_missing(mini_mode_dir, "Electron")


def _run_production_mode(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run backend server that serves API and built SPA on one port."""
    project_root = Path(__file__).parent

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "info",
    ]

    print("Starting production stack...")
    print(f"  Backend API + SPA routes: http://{host}:{port}")
    print("Press Ctrl+C to stop the server.")

    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(project_root),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    processes = [backend_proc]

    def kill_all(*_args, **_kwargs):
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, kill_all)
    signal.signal(signal.SIGTERM, kill_all)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, kill_all)

    try:
        while all(proc.poll() is None for proc in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        kill_all()
        for proc in processes:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


def _reset_runtime_state(project_root: Path) -> None:
    """Delete local DB files and restore default file indexing config."""
    print("Applying runtime reset...")

    db_paths = [
        project_root / "file_registry.db",
        project_root / "local_search.db",
    ]
    for db_path in db_paths:
        if db_path.exists():
            try:
                db_path.unlink()
                print(f"✓ Removed {db_path.name}")
            except OSError as exc:
                print(f"Warning: failed to remove {db_path.name}: {exc}")
        else:
            print(f"- {db_path.name} not found (skipped)")

    config_path = project_root / "config" / "file_indexing.yaml"
    try:
        config_path.write_text(FILE_INDEXING_DEFAULT_CONTENT, encoding="utf-8")
        print("✓ Restored config/file_indexing.yaml to default")
    except OSError as exc:
        print(f"ERROR: failed to restore {config_path}: {exc}")
        sys.exit(1)


def _start_mini_mode_helper(
    host: str,
    port: int,
    *,
    ui_base_url: str | None = None,
) -> subprocess.Popen[Any] | None:
    """Start the Electron mini-mode sidecar used by the global hotkey widget."""
    project_root = Path(__file__).parent
    mini_mode_dir = project_root / "desktop" / "mini-mode"

    if not mini_mode_dir.exists():
        return None

    npm_path = shutil.which("npm")
    if not npm_path:
        print("Warning: npm not found, skipping Mini Mode helper startup.")
        return None

    mini_node_modules = mini_mode_dir / "node_modules"
    if not mini_node_modules.exists():
        print("Mini Mode dependencies not found. Installing in desktop/mini-mode...")
        try:
            subprocess.run([npm_path, "install"], check=True, cwd=mini_mode_dir)
            print("✓ Mini Mode dependencies installed")
        except subprocess.CalledProcessError as exc:
            print(f"Warning: failed to install Mini Mode dependencies: {exc}")
            return None

    mini_env = os.environ.copy()
    app_base_url = ui_base_url or f"http://{host}:{port}"
    mini_env["MINI_MODE_MAIN_URL"] = f"{app_base_url}/chat"
    mini_env["MINI_MODE_WIDGET_URL"] = f"{app_base_url}/mini"

    try:
        proc = subprocess.Popen(
            [npm_path, "start"],
            cwd=mini_mode_dir,
            env=mini_env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except Exception as exc:  # pragma: no cover - best effort launcher path
        print(f"Warning: failed to start Mini Mode helper: {exc}")
        return None

    print(
        "Mini Mode helper started. Use Ctrl+Shift+Space to toggle the widget "
        "while the web UI is running."
    )
    return proc


def setup_environment():
    """Set up the development environment."""
    print("=" * 60)
    print("Setting up Local RAG Application Environment")
    print("=" * 60)

    project_root = Path(__file__).parent

    if not shutil.which("uv"):
        print("ERROR: uv is not installed or not in PATH")
        print("Please install uv: https://docs.astral.sh/uv/")
        sys.exit(1)

    # Check for Node.js and npm
    if not shutil.which("node"):
        print("ERROR: Node.js is not installed or not in PATH")
        print("Please install Node.js from https://nodejs.org/")
        print("If Node.js is installed, make sure it's in your system PATH")
        sys.exit(1)

    if not shutil.which("npm"):
        print("ERROR: npm is not installed or not in PATH")
        print("Please install npm (usually comes with Node.js)")
        print("If npm is installed, make sure it's in your system PATH")
        print("\nTroubleshooting:")
        print("  - Try running 'node --version' and 'npm --version' in your terminal")
        print(
            "  - If they work there, the PATH might not be set correctly for this app"
        )
        sys.exit(1)

    print("\n✓ Runtime environment detected")
    print("✓ uv found")
    print("✓ Node.js found")
    print("✓ npm found")

    # Install uv-managed project dependencies.
    print("\nInstalling uv project dependencies...")
    try:
        subprocess.run(["uv", "sync"], check=True, cwd=project_root)
        print("✓ uv project dependencies installed")
    except Exception as e:
        print(f"ERROR: Failed to install uv project dependencies: {e}")
        sys.exit(1)

    # Install Node.js dependencies
    print("\nInstalling Node.js dependencies...")
    ui_dir = project_root / "ui"
    try:
        # Find npm executable path (works cross-platform)
        npm_path = shutil.which("npm")
        if npm_path:
            subprocess.run([npm_path, "install"], check=True, cwd=ui_dir)
        else:
            # Fallback: use shell execution if path not found
            subprocess.run("npm install", shell=True, check=True, cwd=ui_dir)
        print("✓ Node.js dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install Node.js dependencies: {e}")
        sys.exit(1)

    # Install Electron dependencies
    mini_mode_dir = project_root / "desktop" / "mini-mode"
    if mini_mode_dir.exists():
        print("\nInstalling Electron dependencies...")
        _ensure_electron_deps_ready(mini_mode_dir)
    else:
        print("\nMini mode app not found; skipping Electron dependency install.")

    # Build frontend for production SPA serving.
    print("\nBuilding frontend...")
    try:
        npm_path = shutil.which("npm")
        if npm_path:
            subprocess.run([npm_path, "run", "build"], check=True, cwd=ui_dir)
        else:
            subprocess.run("npm run build", shell=True, check=True, cwd=ui_dir)
        print("✓ Frontend built successfully")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to build frontend: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Setup completed successfully!")
    print("=" * 60)
    print("\nYou can now run the application with:")
    print("  uv run app.py")
    print("=" * 60)


def _run_benchmark(args) -> None:
    """Load benchmark config, bootstrap the app, and run the evaluation suite."""
    import asyncio

    import yaml

    from benchmarks.models import BenchmarkConfig
    from benchmarks.runner import BenchmarkRunner
    from core.bootstrap import bootstrap
    from core.runtime_config import build_runtime_client, resolve_runtime_preferences

    def _normalize_path_fragment(value: str) -> str:
        return value.replace("\\", "/").lower()

    def _infer_dataset_name(path_like: str | None) -> str | None:
        if not path_like:
            return None
        normalized = _normalize_path_fragment(path_like).rstrip("/")
        base = normalized.split("/")[-1]
        if re.fullmatch(r"dataset\d+", base):
            return base
        return None

    def _prompt_expected_paths(prompt: Any) -> list[str]:
        paths: list[str] = []
        if getattr(prompt, "expected_file", None):
            paths.append(str(prompt.expected_file))
        if getattr(prompt, "expected_files", None):
            paths.extend(str(p) for p in (prompt.expected_files or []))
        if getattr(prompt, "expected_citation_file", None):
            paths.append(str(prompt.expected_citation_file))
        return paths

    def _prompt_matches_dataset(prompt: Any, dataset_name: str) -> bool:
        marker = f"/{dataset_name.lower()}/"
        for raw in _prompt_expected_paths(prompt):
            normalized = f"/{_normalize_path_fragment(raw).strip('/')}"
            if marker in normalized + "/":
                return True
        return False

    def _known_embedding_dimension(backend: str, model: str | None) -> int | None:
        model_name = str(model or "").strip().lower()
        if not model_name:
            return None

        if backend == "local":
            local_prefix_dims = {
                "embeddinggemma": 768,
                "nomic-embed-text": 768,
                "mxbai-embed-large": 1024,
                "snowflake-arctic-embed": 1024,
                "bge": 1024,
                "e5": 1024,
            }
            for prefix, dim in local_prefix_dims.items():
                if model_name.startswith(prefix):
                    return dim

        if backend == "api":
            openai_dims = {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
            }
            return openai_dims.get(model_name)

        # Gemini and some providers support configurable dimensions and are better
        # determined via probing; return None here so caller can continue fallback chain.
        return None

    def _infer_backend_from_model_id(
        model_id: str | None,
        *,
        kind: str,
    ) -> str | None:
        value = str(model_id or "").strip().lower()
        if not value:
            return None

        # Gemini naming conventions.
        if value.startswith("models/gemini-") or value.startswith("gemini-"):
            return "gemini"

        # OpenAI naming conventions.
        if value.startswith("text-embedding-") or value.startswith("gpt-"):
            return "api"

        # Voyage embedding model family.
        if kind == "embedding" and value.startswith("voyage-"):
            return "voyage"

        # Heuristic for local/Ollama models (tag-style ids like model:tag).
        if ":" in value:
            return "local"

        local_hints = (
            "llama",
            "qwen",
            "deepseek",
            "phi",
            "mistral",
            "gemma",
            "nomic",
            "embedding",
            "embed",
            "bge",
            "e5",
            "mxbai",
        )
        if any(h in value for h in local_hints):
            return "local"

        return None

    config_path = args.benchmark_config or str(
        Path(__file__).parent / "benchmarks" / "default_benchmark.yaml"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = BenchmarkConfig.from_dict(raw)

    # CLI overrides
    if args.benchmark_dataset:
        config.dataset_path = args.benchmark_dataset

    # Scope benchmark to a single dataset (fast iteration mode).
    scoped_dataset_name = None
    if args.benchmark_dataset_id is not None:
        ds = str(args.benchmark_dataset_id).strip()
        scoped_dataset_name = ds if ds.startswith("dataset") else f"dataset{ds}"
        config.dataset_path = str(Path("datasets") / scoped_dataset_name)
    else:
        inferred = _infer_dataset_name(args.benchmark_dataset)
        if inferred:
            scoped_dataset_name = inferred

    if scoped_dataset_name:
        before = len(config.prompts)
        config.prompts = [
            p for p in config.prompts if _prompt_matches_dataset(p, scoped_dataset_name)
        ]
        if config.dataset_suites:
            scoped_path = _normalize_path_fragment(
                str(Path("datasets") / scoped_dataset_name)
            ).rstrip("/")
            config.dataset_suites = [
                s
                for s in config.dataset_suites
                if _normalize_path_fragment(s.path).rstrip("/") == scoped_path
                or _normalize_path_fragment(s.id).rstrip("/")
                == scoped_dataset_name.lower()
            ]
        print(
            f"Scoped benchmark to {scoped_dataset_name}: {len(config.prompts)}/{before} prompts"
        )
        if not config.prompts:
            raise SystemExit(
                f"No prompts matched {scoped_dataset_name}. Check benchmark config paths."
            )
    if args.benchmark_output:
        config.output_dir = args.benchmark_output
    if args.benchmark_runs is not None:
        config.runs_per_query = args.benchmark_runs
    if args.no_graphs:
        config.no_graphs = True
    if args.skip_indexing:
        config.skip_indexing = True

    print(f"Benchmarking with {len(config.prompts)} prompts from {config_path}")
    print(f"  Dataset:   {config.dataset_path}")
    print(f"  Output:    {config.output_dir}")
    print(f"  Runs/query:{config.runs_per_query}")
    print(f"  Skip idx:  {config.skip_indexing}")
    print()

    ctx = bootstrap()

    prefs = resolve_runtime_preferences(ctx)

    benchmark_target = args.benchmark or "default"
    if benchmark_target in {"local", "api", "gemini"}:
        prefs["embedding_backend"] = benchmark_target
        prefs["inference_backend"] = benchmark_target

    if args.embed:
        prefs["embedding_model"] = args.embed
        inferred_embed_backend = _infer_backend_from_model_id(
            args.embed,
            kind="embedding",
        )
        if inferred_embed_backend in {"local", "api", "gemini", "voyage"}:
            prefs["embedding_backend"] = inferred_embed_backend
    if args.model:
        prefs["inference_model"] = args.model
        inferred_infer_backend = _infer_backend_from_model_id(
            args.model,
            kind="inference",
        )
        if inferred_infer_backend in {"local", "api", "gemini"}:
            prefs["inference_backend"] = inferred_infer_backend

    # Probe the embedding model's native/default vector size so benchmark indexing
    # always uses a matching DB dimension for the selected backend/model.
    probe_prefs = dict(prefs)
    probe_prefs["embedding_dimension"] = None
    embedding_backend = str(probe_prefs.get("embedding_backend") or "")
    embedding_model = str(probe_prefs.get("embedding_model") or "")
    probe_exception: Exception | None = None
    probed_dimension: int | None = None

    for _ in range(2):
        try:
            probe_embed_client = build_runtime_client(
                ctx, kind="embedding", prefs=probe_prefs
            )
            probe_vector = probe_embed_client.embed_text(["benchmark dimension probe"])[
                0
            ]
            probed_dimension = len(probe_vector)
            break
        except Exception as exc:
            probe_exception = exc

    if probed_dimension is None:
        known_dim = _known_embedding_dimension(embedding_backend, embedding_model)
        if known_dim is not None:
            print(
                "Warning: failed to probe embedding dimension for benchmark model "
                f"({probe_exception}). Using known dimension {known_dim} for "
                f"{embedding_backend}/{embedding_model}."
            )
            probed_dimension = known_dim
        else:
            fallback_dimension = int(
                prefs.get("embedding_dimension")
                or getattr(ctx.settings, "embedding_dimension", 3072)
            )
            print(
                "Warning: failed to probe embedding dimension for benchmark model "
                f"({probe_exception}). Falling back to {fallback_dimension}."
            )
            probed_dimension = fallback_dimension

    prefs["embedding_dimension"] = int(probed_dimension)
    try:
        ctx.embedding_client = build_runtime_client(ctx, kind="embedding", prefs=prefs)
        ctx.inference_client = build_runtime_client(ctx, kind="inference", prefs=prefs)
    except Exception as exc:
        message = str(exc).lower()
        if "api key is required" in message and benchmark_target == "default":
            # Default benchmark target should remain usable even when cloud API keys
            # are not configured. Fall back to local backends in that case.
            print(
                "Warning: benchmark default backend requires API key(s) but none were "
                "configured. Falling back to local embedding/inference backends."
            )
            prefs["embedding_backend"] = "local"
            prefs["inference_backend"] = "local"

            if not prefs.get("embedding_model"):
                prefs["embedding_model"] = "embeddinggemma:latest"
            if not prefs.get("inference_model"):
                prefs["inference_model"] = "llama3"

            local_known = _known_embedding_dimension(
                "local", str(prefs.get("embedding_model") or "")
            )
            if local_known is not None:
                prefs["embedding_dimension"] = int(local_known)

            ctx.embedding_client = build_runtime_client(
                ctx, kind="embedding", prefs=prefs
            )
            ctx.inference_client = build_runtime_client(
                ctx, kind="inference", prefs=prefs
            )
        else:
            raise
    ctx.runtime_preferences = prefs

    # Optional dedicated vision model for image-to-text during ingestion.
    # This lets benchmarking use a coding/text model for answer generation while
    # using a separate multimodal model for image description.
    indexing_llm_client = ctx.inference_client
    if args.vlm:
        indexing_llm_client = build_runtime_client(
            ctx,
            kind="inference",
            prefs=prefs,
            model_override=args.vlm,
        )

    print("Benchmark model configuration:")
    print(
        f"  Embedding: {prefs.get('embedding_backend')} / "
        f"{prefs.get('embedding_model')} (dim={prefs.get('embedding_dimension')})"
    )
    print(
        f"  Inference: {prefs.get('inference_backend')} / {prefs.get('inference_model')}"
    )
    if args.vlm:
        print(
            f"  Vision:    {prefs.get('inference_backend')} / {args.vlm} (indexing image-to-text)"
        )
    print()

    runner = BenchmarkRunner(config, ctx, indexing_llm_client=indexing_llm_client)
    asyncio.run(runner.run())


def main():
    parser = argparse.ArgumentParser(description="Local RAG Application")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Set up the environment (uv sync + UI/Electron dependencies + UI build)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Development mode: run backend with hot-reload and frontend dev server (backend on --port, UI on 5173)",
    )
    parser.add_argument(
        "--benchmark",
        nargs="?",
        const="default",
        choices=["default", "local", "api", "gemini"],
        default=None,
        help=(
            "Run benchmark suite. Optional value selects backend preset for both "
            "embedding and inference: default|local|api|gemini."
        ),
    )
    parser.add_argument(
        "--embed",
        type=str,
        default=None,
        help="Override embedding model id for benchmark runs.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override inference model id for benchmark runs.",
    )
    parser.add_argument(
        "--vlm",
        type=str,
        default=None,
        help=(
            "Optional dedicated vision-language model for ingestion image-to-text "
            "during benchmark runs (separate from --model)."
        ),
    )
    parser.add_argument(
        "--benchmark-config",
        type=str,
        default=None,
        help="Path to benchmark YAML config (default: benchmarks/default_benchmark.yaml).",
    )
    parser.add_argument(
        "--benchmark-dataset",
        type=str,
        default=None,
        help="Override the dataset path in the benchmark config.",
    )
    parser.add_argument(
        "--benchmark-dataset-id",
        type=str,
        default=None,
        help=(
            "Run benchmark against a single dataset folder and matching prompts "
            "(e.g. 13 or dataset13)."
        ),
    )
    parser.add_argument(
        "--benchmark-output",
        type=str,
        default=None,
        help="Override the output directory for benchmark results.",
    )
    parser.add_argument(
        "--benchmark-runs",
        type=int,
        default=None,
        help="Override the number of runs per query.",
    )
    parser.add_argument(
        "--no-graphs",
        action="store_true",
        help="Skip graph generation during benchmarking.",
    )
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="Skip dataset indexing and run queries against existing index.",
    )
    parser.add_argument(
        "--electron",
        dest="electron",
        action="store_true",
        help=(
            "Run development mode with Electron mini-mode helper (equivalent to "
            "--dev --electron)."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Reset local runtime state before running: remove file_registry.db and "
            "local_search.db from project root, and restore config/file_indexing.yaml defaults."
        ),
    )

    args = parser.parse_args()
    project_root = Path(__file__).parent

    if args.reset:
        _reset_runtime_state(project_root)

    # Ensure file_indexing.yaml exists (create default template if missing)
    config_path = project_root / "config" / "file_indexing.yaml"
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(FILE_INDEXING_DEFAULT_CONTENT, encoding="utf-8")
        print("✓ Created config/file_indexing.yaml with default template")

    if args.setup:
        setup_environment()
        # After setup, continue only when another explicit action was requested.
        if not args.dev and not args.electron and args.benchmark is None:
            return

    if args.benchmark is not None:
        _run_benchmark(args)
        return

    if args.electron:
        _run_dev_mode(host=args.host, port=args.port, with_electron=True)
        return

    if args.dev:
        _run_dev_mode(host=args.host, port=args.port, with_electron=False)
        return

    # Production default: no flags starts backend that also serves the SPA.
    _run_production_mode(
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
