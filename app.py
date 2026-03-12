"""Main application entrypoint."""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import venv
from pathlib import Path


def _run_dev_mode(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run backend (uvicorn --reload) and frontend (npm run dev) for development."""
    project_root = Path(__file__).parent
    ui_dir = project_root / "ui"
    venv_path = project_root / ".venv"

    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"
    else:
        venv_python = venv_path / "bin" / "python"

    if not venv_python.exists():
        print("ERROR: Virtual environment not found. Run: python app.py --setup")
        sys.exit(1)

    if not (ui_dir / "node_modules").exists():
        print("Node dependencies not found. Run: python app.py --setup")
        sys.exit(1)

    # Backend: uvicorn with --reload
    backend_cmd = [
        str(venv_python),
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
    print("Press Ctrl+C to stop both.")

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

    def kill_both(*_args, **_kwargs):
        backend_proc.terminate()
        frontend_proc.terminate()

    signal.signal(signal.SIGINT, kill_both)
    signal.signal(signal.SIGTERM, kill_both)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, kill_both)

    try:
        while backend_proc.poll() is None and frontend_proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    kill_both()
    backend_proc.wait()
    frontend_proc.wait()


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH (cross-platform)."""
    # Use shutil.which for cross-platform command detection
    if shutil.which(command) is not None:
        return True

    # Fallback: try running the command to verify it works
    try:
        subprocess.run(
            [command, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=5,
        )
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def setup_environment():
    """Set up the development environment."""
    print("=" * 60)
    print("Setting up Local RAG Application Environment")
    print("=" * 60)

    project_root = Path(__file__).parent
    venv_path = project_root / ".venv"

    # Check for Python
    if not check_command_exists("python3") and not check_command_exists("python"):
        print("ERROR: Python 3 is not installed or not in PATH")
        print("Please install Python 3.10 or higher from https://www.python.org/")
        sys.exit(1)

    python_cmd = "python3" if check_command_exists("python3") else "python"

    # Check for Node.js and npm
    if not check_command_exists("node"):
        print("ERROR: Node.js is not installed or not in PATH")
        print("Please install Node.js from https://nodejs.org/")
        print("If Node.js is installed, make sure it's in your system PATH")
        sys.exit(1)

    if not check_command_exists("npm"):
        print("ERROR: npm is not installed or not in PATH")
        print("Please install npm (usually comes with Node.js)")
        print("If npm is installed, make sure it's in your system PATH")
        print("\nTroubleshooting:")
        print("  - Try running 'node --version' and 'npm --version' in your terminal")
        print(
            "  - If they work there, the PATH might not be set correctly for Python subprocess"
        )
        sys.exit(1)

    print(f"\n✓ Python found: {python_cmd}")
    print("✓ Node.js found")
    print("✓ npm found")

    # Create virtual environment if it doesn't exist
    if not venv_path.exists():
        print(f"\nCreating Python virtual environment at {venv_path}...")
        venv.create(venv_path, with_pip=True)
        print("✓ Virtual environment created")
    else:
        print(f"\n✓ Virtual environment already exists at {venv_path}")

    # Determine the correct pip and python paths for the venv (cross-platform)
    # Python's venv module handles this automatically, but we need the paths
    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"  # noqa
        venv_pip = venv_path / "Scripts" / "pip.exe"
    else:
        venv_python = venv_path / "bin" / "python"  # noqa
        venv_pip = venv_path / "bin" / "pip"

    # Install Python dependencies
    print("\nInstalling Python dependencies...")
    try:
        # Check if uv is available
        if check_command_exists("uv"):
            print("Using uv to install dependencies...")
            subprocess.run(["uv", "sync"], check=True, cwd=project_root)
        else:
            print("uv not found. Installing dependencies with pip...")
            pyproject_file = project_root / "pyproject.toml"
            with open(pyproject_file, "rb") as f:
                pyproject_data = tomllib.load(f)

            dependencies = pyproject_data["project"]["dependencies"]
            subprocess.run(
                [str(venv_pip), "install"] + dependencies, check=True, cwd=project_root
            )
        print("✓ Python dependencies installed")
    except Exception as e:
        print(f"ERROR: Failed to install Python dependencies: {e}")
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

    # Build frontend
    print("\nBuilding frontend...")
    try:
        # Find npm executable path (works cross-platform)
        npm_path = shutil.which("npm")
        if npm_path:
            subprocess.run([npm_path, "run", "build"], check=True, cwd=ui_dir)
        else:
            # Fallback: use shell execution if path not found
            subprocess.run("npm run build", shell=True, check=True, cwd=ui_dir)
        print("✓ Frontend built successfully")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to build frontend: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Setup completed successfully!")
    print("=" * 60)
    print("\nYou can now run the application with:")
    print("  python3 app.py --webui")
    print("\nOr activate the virtual environment first:")
    if sys.platform == "win32":
        print("  .venv\\Scripts\\activate")
    else:
        print("  source .venv/bin/activate")
    print("=" * 60)


def _run_benchmark(args) -> None:
    """Load benchmark config, bootstrap the app, and run the evaluation suite."""
    import asyncio

    import yaml

    from benchmarks.models import BenchmarkConfig
    from benchmarks.runner import BenchmarkRunner
    from core.bootstrap import bootstrap

    config_path = args.benchmark_config or str(
        Path(__file__).parent / "benchmarks" / "default_benchmark.yaml"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = BenchmarkConfig.from_dict(raw)

    # CLI overrides
    if args.benchmark_dataset:
        config.dataset_path = args.benchmark_dataset
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
    runner = BenchmarkRunner(config, ctx)
    asyncio.run(runner.run())


def main():
    parser = argparse.ArgumentParser(description="Local RAG Application")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Set up the environment (install dependencies, build frontend)",
    )
    parser.add_argument(
        "--webui", action="store_true", help="Launch the web UI with backend server"
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
        action="store_true",
        help="Run the benchmark evaluation suite (bypasses all UI).",
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

    args = parser.parse_args()

    if args.setup:
        setup_environment()
        # After setup, continue to launch web UI if requested
        if not args.webui:
            return

    if args.dev:
        _run_dev_mode(host=args.host, port=args.port)
        return

    if args.benchmark:
        _run_benchmark(args)
        return

    if args.webui:
        ui_dir = Path(__file__).parent / "ui"
        ui_build_path = ui_dir / "dist"
        node_modules_path = ui_dir / "node_modules"

        # Check if Node.js dependencies are installed
        if not node_modules_path.exists():
            print("Node.js dependencies not found. Installing...")
            os.chdir(ui_dir)
            try:
                # Find npm executable path (works cross-platform)
                npm_path = shutil.which("npm")
                if npm_path:
                    subprocess.run([npm_path, "install"], check=True)
                else:
                    # Fallback: use shell execution if path not found
                    subprocess.run("npm install", shell=True, check=True)
                print("✓ Node.js dependencies installed")
            except subprocess.CalledProcessError:
                print("Error installing Node.js dependencies.")
                print("Please run 'npm install' in the ui/ directory.")
                sys.exit(1)
            except FileNotFoundError:
                print("npm not found. Please install Node.js and npm.")
                sys.exit(1)
            finally:
                os.chdir(Path(__file__).parent)

        # Check if frontend is built
        if not ui_build_path.exists():
            print("Frontend not built. Building frontend...")
            os.chdir(ui_dir)
            try:
                # Find npm executable path (works cross-platform)
                npm_path = shutil.which("npm")
                if npm_path:
                    subprocess.run([npm_path, "run", "build"], check=True)
                else:
                    # Fallback: use shell execution if path not found
                    subprocess.run("npm run build", shell=True, check=True)
                print("✓ Frontend built successfully!")
            except subprocess.CalledProcessError:
                print("Error building frontend.")
                print("Please run 'npm run build' in the ui/ directory.")
                sys.exit(1)
            except FileNotFoundError:
                print("npm not found. Please install Node.js and npm.")
                sys.exit(1)
            finally:
                os.chdir(Path(__file__).parent)

        print(f"Starting web UI server on http://{args.host}:{args.port}")
        print("Press Ctrl+C to stop the server")

        # Check if we're using the venv's Python, and if not, suggest using it
        venv_path = Path(__file__).parent / ".venv"
        using_venv_python = False

        if venv_path.exists():
            if sys.platform == "win32":
                venv_python = venv_path / "Scripts" / "python.exe"
            else:
                venv_python = venv_path / "bin" / "python"

            # Check if current Python is from venv
            current_python = Path(sys.executable).resolve()
            venv_python_resolved = (
                venv_python.resolve() if venv_python.exists() else None
            )

            if venv_python_resolved and current_python == venv_python_resolved:
                using_venv_python = True

        # Import dependencies only when needed (after setup)
        try:
            import uvicorn

            from backend.main import app
        except ImportError as e:
            print(f"ERROR: Required dependencies not installed: {e}")
            print(
                "\nThe issue is that the Python interpreter you're using doesn't have the dependencies."
            )

            if venv_path.exists() and not using_venv_python:
                print("\nSolution: Use the virtual environment's Python directly:")
                if sys.platform == "win32":
                    venv_python = venv_path / "Scripts" / "python.exe"
                    print(f"  {venv_python} app.py --webui")
                else:
                    venv_python = venv_path / "bin" / "python"
                    print(f"  {venv_python} app.py --webui")
            else:
                print("\nTroubleshooting:")
                print("1. Make sure you've run: python3 app.py --setup")
                print("2. If using a virtual environment, activate it first:")
                if sys.platform == "win32":
                    print("   .venv\\Scripts\\activate")
                    print("   Then use: python app.py --webui")
                else:
                    print("   source .venv/bin/activate")
                    print("   Then use: python app.py --webui")
                print("3. Or use the venv's Python directly:")
                if sys.platform == "win32":
                    print("   .venv\\Scripts\\python.exe app.py --webui")
                else:
                    print("   .venv/bin/python app.py --webui")
            sys.exit(1)

        # Run the FastAPI server with static file serving
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    else:
        print("Use --webui flag to launch the web interface")
        parser.print_help()


if __name__ == "__main__":
    main()
