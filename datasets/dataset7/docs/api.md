# API Reference

## POST /api/search
Search indexed documents.

**Request:**
```json
{"query": "string", "top_k": 5}
```

**Response:**
```json
{"results": [...], "count": 5}
```

## POST /api/index
Index a new document.

## GET /api/health
Health check endpoint.
