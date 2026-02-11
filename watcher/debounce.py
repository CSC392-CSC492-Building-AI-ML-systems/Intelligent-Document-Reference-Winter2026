"""Event debouncing utilities for file system events.

Debouncing prevents duplicate processing of rapid file changes.
"""
import threading
import time
from typing import Callable, Dict, Optional, Tuple, List
from watcher.events import FileEvent


class DebounceHandler:
    """Debounce handler for file system events."""
    
    def __init__(self, delay: float, callback: Callable[[FileEvent], None]):
        """
        Initialize debounce handler.
        
        Args:
            delay: Delay in seconds before processing events
            callback: Function to call with debounced events
        """
        self.delay = delay
        self.callback = callback
        self._pending: Dict[str, Tuple[FileEvent, threading.Timer]] = {}
        self._lock = threading.Lock()
    
    def add_event(self, event: FileEvent):
        """
        Add an event to be debounced.
        
        Args:
            event: File event to debounce
        """
        with self._lock:
            # Cancel existing timer for this path
            if event.path in self._pending:
                _, timer = self._pending[event.path]
                timer.cancel()
            
            # Create new timer
            timer = threading.Timer(self.delay, self._fire_event, args=[event])
            self._pending[event.path] = (event, timer)
            timer.start()
    
    def _fire_event(self, event: FileEvent):
        """Fire the event after debounce delay."""
        with self._lock:
            # Remove from pending
            if event.path in self._pending:
                del self._pending[event.path]
        
        # Call the callback outside the lock to avoid deadlock
        try:
            self.callback(event)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error processing event: {e}", exc_info=True)
    
    def flush(self):
        """Flush all pending events immediately."""
        events_to_fire = []
        with self._lock:
            for event, timer in self._pending.values():
                timer.cancel()
                events_to_fire.append(event)
            self._pending.clear()
        
        # Fire events outside the lock
        for event in events_to_fire:
            try:
                self.callback(event)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error processing event: {e}", exc_info=True)


def debounce(events: List[FileEvent], delay: float = 2.0) -> List[FileEvent]:
    """
    Debounce a list of events by path.
    
    This is a simple implementation that keeps only the most recent event
    for each path within the time window.
    
    Args:
        events: List of file events to debounce
        delay: Time window for deduplication (seconds)
        
    Returns:
        Deduplicated list of events
    """
    if not events:
        return []
    
    # Group events by path, keeping only the most recent
    path_events: Dict[str, FileEvent] = {}
    current_time = time.time()
    
    for event in events:
        # Simple deduplication: last event per path wins
        path_events[event.path] = event
    
    return list(path_events.values())

