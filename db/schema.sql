-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- 1. Files Table
-- Tracks the source documents on disk
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    file_hash TEXT,             -- specific hash (e.g., md5/sha256) to detect content changes
    size_bytes INTEGER,
    last_modified_timestamp REAL, -- from os.stat
    last_indexed_at DATETIME,
    status TEXT DEFAULT 'pending' -- pending, indexed, failed, outdated
);

-- 2. File Versions / History
-- Supports incremental reindexing by tracking state over time
CREATE TABLE IF NOT EXISTS file_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    version_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- 3. Chunks Table
-- Relational storage of text content. 
-- Changed to INTEGER PK to alias rowid for efficient mapping to vec_items
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT UNIQUE,        -- UUID strings kept for external referencing
    file_id INTEGER NOT NULL,
    version_id INTEGER,         -- Link to specific version of file
    chunk_index INTEGER,
    start_offset INTEGER,
    end_offset INTEGER,
    text_content TEXT NOT NULL,
    page_number INTEGER,        -- Source page (PDFs); NULL for non-paged docs
    section TEXT,               -- Section hierarchy e.g. "Chapter 1 > Methods"
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY(version_id) REFERENCES file_versions(id)
);

-- 4. Labels / Tags
-- System or User defined tags for filtering
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT DEFAULT 'user' -- 'system' or 'user'
);

-- Many-to-Many relationship between Files and Labels
CREATE TABLE IF NOT EXISTS file_labels (
    file_id INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    PRIMARY KEY (file_id, label_id),
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY(label_id) REFERENCES labels(id) ON DELETE CASCADE
);

-- 5. Inclusion/Exclusion Rules
-- Configurable rules for the crawler/indexer
CREATE TABLE IF NOT EXISTS indexing_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,      -- glob pattern e.g., "*.py", "**/node_modules/**"
    action TEXT NOT NULL,       -- 'include' or 'exclude'
    priority INTEGER DEFAULT 0
);

-- 6. Jobs Table
-- Central queue for indexing jobs from watcher and UI
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,        -- dedup key: one active job per file
    source TEXT NOT NULL DEFAULT 'watcher', -- 'watcher' or 'ui'
    priority INTEGER NOT NULL DEFAULT 1,   -- higher = dequeued first (ui=10, watcher=1)
    status TEXT NOT NULL DEFAULT 'queued',  -- queued, running, completed, failed
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
    ON jobs (status, priority DESC, created_at ASC);

-- 7. Vector Table (sqlite-vec)
-- rowid of this table will MATCH rowid (id) of 'chunks' table
CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(
    embedding float[3072]
);

-- 8. Settings Table (key-value store for UI/app settings)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
