# Getting Started

## Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- SQLite 3.35+ (with vector extensions)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/example/doc-search.git
   cd doc-search
   ```

2. Install Python dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

3. Initialize the database:
   ```bash
   python -m scripts.dev_bootstrap
   ```

4. Start the development server:
   ```bash
   python app.py
   ```

## First Steps

### Indexing Documents
Place your documents in the `datasets/` directory and run:
```bash
python -m scripts.seed_index --path datasets/my_folder
```

### Querying
Open the web UI at `http://localhost:5173` or use the API:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is retrieval-augmented generation?"}'
```
