# Local-first Intelligent Document Reference — Architecture

A local-first RAG (Retrieval-Augmented Generation) system with an intelligent document reference interface.

## Quick Start

### Option 1: Automated Setup (Recommended)

The easiest way to get started is using the automated setup:

```bash
python3 app.py --setup --webui
```

This will:
- Create a Python virtual environment
- Install all Python dependencies
- Install Node.js dependencies
- Build the frontend
- Launch the web UI


For Benchmarking

```bash
python app.py --benchmark                          # run with defaults
python app.py --benchmark --skip-indexing           # skip re-indexing
python app.py --benchmark --benchmark-config my.yaml --no-graphs
python app.py --benchmark --benchmark-runs 1 --benchmark-output results/
```
### Option 2: Manual Setup

If you prefer to set up manually, see the [Installation](#installation) section below.

## Installation

### Prerequisites

- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
- **Node.js 18+ and npm** - [Download Node.js](https://nodejs.org/)
- **Git** (optional, for cloning the repository)

**Folder picker (Browse in Settings):** The native folder picker needs a Python built with Tcl/Tk (tkinter). If you see "Folder picker not available", see [Using the folder picker (tkinter)](docs/TKINTER_SETUP.md) to install Python with tkinter and recreate the virtual environment.

### Automated Setup

Run the setup script to automatically configure everything:

```bash
python3 app.py --setup
```

This will:
1. Check for required tools (Python, Node.js, npm)
2. Create a Python virtual environment (`.venv`)
3. Install Python dependencies (using uv if available, otherwise pip)
4. Install Node.js dependencies in the `ui/` directory
5. Build the frontend application

After setup, launch the application using the **virtual environment's Python** (dependencies like `uvicorn` are installed there):

```bash
.venv/bin/python app.py --webui
```

On Windows: `.venv\Scripts\python app.py --webui`

### Manual Setup

#### 1. Python Environment Setup

Create and activate a virtual environment:

**On Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**On Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

#### 2. Install Python Dependencies

**Using uv (recommended):**
```bash
uv sync
```

**Using pip:**
```bash
pip install .
```

#### 3. Install Node.js Dependencies

```bash
cd ui
npm install
cd ..
```

#### 4. Build Frontend

```bash
cd ui
npm run build
cd ..
```

## Running the Application

### Launch Web UI

After setup, launch the web interface using the virtual environment’s Python (so dependencies like `uvicorn` are found):

**macOS/Linux:**
```bash
.venv/bin/python app.py --webui
```

**Windows:**
```bash
.venv\Scripts\python app.py --webui
```

**Using uv:** If you use [uv](https://github.com/astral-sh/uv), you can run without activating the venv (e.g. `uv run app.py --webui`); uv handles the environment.

The application will be available at `http://127.0.0.1:8000`

### Custom Host/Port

You can specify a custom host and port:

```bash
.venv/bin/python app.py --webui --host 0.0.0.0 --port 8080
```

### Command Line Options

```bash
python3 app.py [OPTIONS]

Options:
  --setup          Set up the environment (install dependencies, build frontend)
  --webui          Launch the web UI with backend server
  --dev            Development mode: backend (hot-reload) + frontend dev server (backend on --port, UI on 5173)
  --host HOST      Host to bind the server to (default: 127.0.0.1)
  --port PORT      Port to bind the server to (default: 8000)
  -h, --help       Show help message
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (you can copy from `.env.example` if it exists) to configure:

- `DATABASE_URL`: Database connection string (default: `sqlite:///./data/metadata.db`)
- `VECTOR_DB_PATH`: Path to vector database (default: `./data/vectorstore`)
- `OLLAMA_URL`: Ollama API URL (default: `http://localhost:11434`)
- `DOCUMENT_PATH`: Path to documents directory for file indexing (default: current directory)

### API Configuration

The backend API runs on `http://127.0.0.1:8000` by default. You can change the host and port using command-line arguments.

## Troubleshooting

### Python Virtual Environment Issues

If you encounter issues with the virtual environment:

```bash
# Remove and recreate the virtual environment
rm -rf .venv
python3 app.py --setup
```

### Node.js Dependencies Issues

If frontend dependencies fail to install:

```bash
cd ui
rm -rf node_modules package-lock.json
npm install
npm run build
cd ..
```

### Port Already in Use

If port 8000 is already in use, specify a different port:

```bash
.venv/bin/python app.py --webui --port 8080
```

### Frontend Not Loading

If the frontend doesn't load:
1. Check that the frontend is built: `ls ui/dist`
2. Rebuild if needed: `cd ui && npm run build && cd ..`
3. Check browser console for errors

## Development

### Running in Development Mode

Use the **`--dev`** flag to run both the backend (with hot-reload) and the frontend dev server in one go. The backend runs on the usual port (default 8000), the UI on port 5173, and the frontend is configured to talk to the backend.

**macOS/Linux:**
```bash
.venv/bin/python app.py --dev
```

**Windows:**
```bash
.venv\Scripts\python app.py --dev
```

Open http://localhost:5173 for the UI; API is at http://127.0.0.1:8000. Press Ctrl+C to stop both processes. You don’t need to run `npm run build` while using `--dev`; the dev server picks up frontend and backend changes automatically.

If you prefer to run them separately (e.g. in two terminals), run the backend with:

```bash
.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

and in another terminal:

```bash
cd ui && npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` in the environment if the frontend needs to point at the backend.

### Testing the inclusion folder (watcher)

1. **Start the app** (from project root). For production-style single server:
   ```bash
   .venv/bin/python app.py --webui
   ```
   For development with hot-reload, use `--dev` (see [Running in Development Mode](#running-in-development-mode)).

2. **In the browser**: Open the app (e.g. http://127.0.0.1:8000 or http://localhost:5173), go to **Settings** → **File Indexing**.

3. **Set the inclusion folder**: In "Inclusion folder path", enter an absolute path to a real folder (e.g. `/Users/you/Intelligent-Document-Reference-Winter2026` or `C:\path\to\project` on Windows). Click **Set inclusion folder**. You should see a success message.

4. **Verify via API** (optional):
   ```bash
   curl -s http://localhost:8000/watcher/path
   ```
   You should see `active_paths` containing your path. To test POST directly:
   ```bash
   curl -s -X POST http://localhost:8000/watcher/path \
     -H "Content-Type: application/json" \
     -d '{"path":"/tmp/test_watch_folder","excluded_files":[]}'
   ```
   Use a path that exists on your machine; the backend returns 400 if the path does not exist.

### Project Structure

## Final Directory Structure

```
├── app.py
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── settings.py
│   ├── models.yaml
│   └── paths.yaml
├── core/
│   ├── bootstrap.py
│   ├── wiring.py
│   ├── lifecycle.py
│   └── context.py
├── model_clients/
│   ├── base.py
│   ├── openai_client.py
│   ├── google_client.py
│   ├── ollama_client.py
│   ├── registry.py
│   └── errors.py
├── embeddings/
│   ├── base.py
│   ├── router.py
│   └── embedder.py
├── inference/
│   ├── retriever.py
│   ├── rag.py
│   ├── citation.py
│   ├── router.py
│   └── responder.py
├── backend/
│   ├── main.py
│   ├── api/
│   │   ├── routes_chat.py
│   │   ├── routes_files.py
│   │   ├── routes_jobs.py
│   │   └── routes_settings.py
│   ├── deps.py
│   └── schemas.py
├── ingestion/
│   ├── extractors/
│   ├── chunking/
│   ├── pipeline.py
│   └── indexer.py
├── db/
│   ├── metadata.py
│   ├── vectorstore.py
│   ├── settings_store.py
│   ├── schema.sql
│   └── migrations/
├── watcher/
│   ├── watcher.py
│   ├── debounce.py
│   └── events.py
├── jobs/
│   ├── queue.py
│   ├── scheduler.py
│   ├── worker.py
│   └── state.py
├── ui/
│   ├── web/
│   │   ├── frontend/
│   │   │   └── components/
│   │   │       └── SettingsPanel.tsx
│   │   └── static/
│   └── widget/
│       └── launcher.py
├── mcp/
│   ├── server.py
│   └── tools.py
├── evaluation/
│   ├── datasets/
│   ├── queries.yaml
│   ├── accuracy.py
│   └── benchmarks.py
├── scripts/
│   ├── preprocess.py
│   ├── reindex.py
│   └── dev_bootstrap.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── corpus/
    │   └── expected/
    ├── unit/
    │   ├── model_clients/
    │   ├── embeddings/
    │   ├── inference/
    │   ├── ingestion/
    │   ├── db/
    │   └── core/
    ├── integration/
    └── e2e/
```

### `config/`
Configuration management: settings loading, model definitions, and path configurations.

### `core/`
Application core: dependency injection context, bootstrap logic, wiring, and lifecycle management.

### `model_clients/`
Provider-agnostic model client abstractions: base interfaces, provider implementations (OpenAI, Google, Ollama), and a registry for client selection.

### `embeddings/`
Embedding facade layer: router for selecting embedding clients and high-level embedding API.

### `inference/`
Inference and retrieval layer: RAG orchestration, retrieval, citation formatting, and response generation.

### `backend/`
FastAPI backend: REST API routes for chat, files, jobs, and settings management.

### `ingestion/`
Document ingestion pipeline: extractors, chunking algorithms, and indexing orchestration.

### `db/`
Database layer: metadata storage, vector store, settings persistence, and schema definitions.

### `watcher/`
Filesystem monitoring: file watcher, event debouncing, and normalized event types.

### `jobs/`
Job processing: queue abstraction, scheduler, async workers, and job state management.

### `ui/`
User interfaces: web frontend components and widget launcher.

### `mcp/`
MCP server: Model Context Protocol server exposing retrieval and Q&A tools.

### `evaluation/`
Evaluation harness: accuracy testing, benchmarks, and evaluation datasets.

### `scripts/`
Utility scripts: preprocessing, reindexing, and developer bootstrap helpers.

### `tests/`
Test suite: unit tests, integration tests, end-to-end tests, and test fixtures.
