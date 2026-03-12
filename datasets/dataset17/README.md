# Dataset 17 – Multi-language Nested Project

A polyglot project with Rust (deeply nested crate/module structure),
Go (cmd/internal layout), and TypeScript/React (component hierarchy).
Tests the indexer's ability to handle mixed languages across deep nesting.

## Languages
- Rust: `crates/core/src/` (4 levels deep)
- Go: `services/search-api/` (cmd/server + internal/handler/middleware)
- TypeScript/React: `frontend/src/` (pages/components/hooks/utils/styles)
