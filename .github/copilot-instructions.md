# Central Job Queue for Watcher & Indexing Jobs

## Overview

This document describes the architecture and implementation of the Central Job Queue system that coordinates file system watching and document indexing operations in the Intelligent Document Reference system.

## Architecture

### Components

1. **Job Queue (`jobs/queue.py`)**
   - Thread-safe, priority-based job queue
   - Job deduplication to prevent redundant processing
   - Support for multiple job types (watcher events, indexing tasks)
   - In-memory queue with optional persistence

2. **Job Worker (`jobs/worker.py`)**
   - Async worker process that consumes jobs from the queue
   - Executes job handlers based on job type
   - Error handling and retry logic
   - Graceful shutdown support

3. **Job Scheduler (`jobs/scheduler.py`)**
   - Schedules jobs with deduplication
   - Manages job priorities
   - Coordinates between watcher events and indexing tasks

4. **Job State (`jobs/state.py`)**
   - Tracks job status (pending, running, completed, failed)
   - Persists job history and results
   - Provides job status queries

### Job Types

1. **Watcher Jobs**
   - File created/modified events
   - File deleted events
   - Directory change events
   - Debounced to reduce redundant processing

2. **Indexing Jobs**
   - Document extraction
   - Text chunking
   - Embedding generation
   - Vector store persistence
   - Metadata updates

## Job Flow

```
File System Change
    ↓
Watcher (watchdog)
    ↓
Debounce Events
    ↓
Create Job(s)
    ↓
Job Queue (with deduplication)
    ↓
Job Scheduler (priority sorting)
    ↓
Worker Pool
    ↓
Job Handlers (indexing pipeline, etc.)
    ↓
Update Job State
```

## Job Model

Each job contains:
- `job_id`: Unique identifier
- `job_type`: Type of job (e.g., "index_document", "delete_document")
- `priority`: Priority level (higher = more urgent)
- `payload`: Job-specific data (file path, options, etc.)
- `status`: Current status (pending, running, completed, failed)
- `created_at`: Timestamp when job was created
- `started_at`: Timestamp when job started processing
- `completed_at`: Timestamp when job completed
- `error`: Error message if job failed
- `retry_count`: Number of retry attempts

## Deduplication Strategy

- Jobs with the same `job_type` and `payload` within a time window are deduplicated
- Most recent job supersedes older pending jobs for the same file
- Running jobs are not deduplicated

## Priority Levels

1. **High (3)**: User-initiated operations, critical updates
2. **Normal (2)**: Regular file changes, scheduled indexing
3. **Low (1)**: Background maintenance, batch operations

## Integration Points

### Watcher Integration
```python
from jobs.queue import enqueue
from jobs.scheduler import schedule

# When file changes are detected
def on_file_changed(event):
    job = {
        'job_type': 'index_document',
        'payload': {'path': event.path},
        'priority': 2
    }
    schedule(job)  # Handles deduplication and enqueuing
```

### Indexing Integration
```python
from ingestion.pipeline import run_index

# Job handler for indexing
async def handle_index_job(job):
    path = job['payload']['path']
    ctx = get_context()
    await run_index(path, ctx)
```

## Error Handling

- Failed jobs are retried up to 3 times with exponential backoff
- Persistent failures are logged and marked as failed
- Dead letter queue for jobs that exceed retry limit
- Health monitoring and alerting for queue backlog

## Performance Considerations

- Queue size limits to prevent memory overflow
- Worker pool size configurable based on system resources
- Batch processing for multiple related jobs
- Rate limiting for external API calls (embedding generation)

## Testing Strategy

1. **Unit Tests**
   - Queue operations (enqueue, dequeue, deduplication)
   - Job state transitions
   - Scheduler logic

2. **Integration Tests**
   - End-to-end watcher → queue → indexing flow
   - Concurrent job processing
   - Error handling and retry logic

3. **Performance Tests**
   - Queue throughput under load
   - Worker scalability
   - Memory usage profiling

## Future Enhancements

- Persistent queue (Redis, database)
- Distributed workers across multiple processes/machines
- Job result streaming and progress updates
- Web UI for job monitoring and management
- Job cancellation support
- Job dependency management (job chains/DAGs)
