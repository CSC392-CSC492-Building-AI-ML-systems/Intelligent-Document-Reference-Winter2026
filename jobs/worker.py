"""Async worker process for processing jobs from the queue."""
import asyncio
import logging
import signal
from typing import Callable, Dict, Optional, Any

from jobs.queue import JobQueue, Job, JobStatus, get_queue


logger = logging.getLogger(__name__)


class Worker:
    """Async worker that processes jobs from the queue."""
    
    def __init__(
        self,
        queue: Optional[JobQueue] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        poll_interval: float = 0.1
    ):
        """
        Initialize worker.
        
        Args:
            queue: Job queue to process (uses global queue if None)
            max_retries: Maximum retry attempts for failed jobs
            retry_delay: Initial delay between retries (exponential backoff)
            poll_interval: Polling interval for queue checks (seconds)
        """
        self._queue = queue or get_queue()
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._poll_interval = poll_interval
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def register_handler(self, job_type: str, handler: Callable):
        """
        Register a handler for a specific job type.
        
        Args:
            job_type: Type of job this handler processes
            handler: Async function that processes the job
        """
        self._handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type}")
    
    async def start(self):
        """Start the worker."""
        if self._running:
            logger.warning("Worker is already running")
            return
        
        self._running = True
        logger.info("Worker started")
        
        # Set up signal handlers for graceful shutdown
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        except NotImplementedError:
            # Signal handlers not supported on Windows
            pass
        
        # Start processing loop
        self._task = asyncio.create_task(self._process_loop())
    
    async def stop(self):
        """Stop the worker gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping worker...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Worker stopped")
    
    async def _process_loop(self):
        """Main processing loop."""
        while self._running:
            try:
                # Poll for jobs with timeout
                job = await asyncio.get_event_loop().run_in_executor(
                    None, self._queue.dequeue, self._poll_interval
                )
                
                if job:
                    await self._process_job(job)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Backoff on error
    
    async def _process_job(self, job: Job):
        """
        Process a single job.
        
        Args:
            job: Job to process
        """
        logger.info(f"Processing job {job.job_id} (type: {job.job_type})")
        
        # Get handler
        handler = self._handlers.get(job.job_type)
        if not handler:
            error_msg = f"No handler registered for job type: {job.job_type}"
            logger.error(error_msg)
            self._queue.update_job_status(job.job_id, JobStatus.FAILED, error_msg)
            return
        
        # Process with retry logic
        retry_count = 0
        while retry_count <= self._max_retries:
            try:
                # Execute handler
                await handler(job)
                
                # Mark as completed
                self._queue.update_job_status(job.job_id, JobStatus.COMPLETED)
                logger.info(f"Job {job.job_id} completed successfully")
                return
                
            except Exception as e:
                retry_count += 1
                error_msg = f"Job {job.job_id} failed (attempt {retry_count}/{self._max_retries + 1}): {e}"
                logger.error(error_msg, exc_info=True)
                
                if retry_count <= self._max_retries:
                    # Exponential backoff
                    delay = self._retry_delay * (2 ** (retry_count - 1))
                    logger.info(f"Retrying job {job.job_id} in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Max retries exceeded
                    self._queue.update_job_status(job.job_id, JobStatus.FAILED, str(e))
                    logger.error(f"Job {job.job_id} failed after {self._max_retries} retries")


def run_worker(ctx: Optional[Any] = None):
    """
    Run worker in async context.
    
    Args:
        ctx: Optional application context
    """
    worker = Worker()
    
    # Register default handlers
    _register_default_handlers(worker, ctx)
    
    # Run worker
    async def _run():
        await worker.start()
        try:
            # Keep running until stopped
            while worker._running:
                await asyncio.sleep(1)
        finally:
            await worker.stop()
    
    asyncio.run(_run())


def _register_default_handlers(worker: Worker, ctx: Optional[Any] = None):
    """Register default job handlers."""
    
    async def index_document_handler(job: Job):
        """Handler for document indexing jobs."""
        from ingestion.pipeline import run_index
        
        path = job.payload.get('path')
        if not path:
            raise ValueError("Missing 'path' in job payload")
        
        await asyncio.get_event_loop().run_in_executor(
            None, run_index, path, ctx
        )
    
    async def delete_document_handler(job: Job):
        """Handler for document deletion jobs."""
        # Placeholder for deletion logic
        path = job.payload.get('path')
        logger.info(f"Delete document handler called for: {path}")
        # TODO: Implement document deletion from vector store
    
    worker.register_handler("index_document", index_document_handler)
    worker.register_handler("delete_document", delete_document_handler)
