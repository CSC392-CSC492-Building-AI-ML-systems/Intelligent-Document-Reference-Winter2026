"""Unit tests for watcher functionality."""
import time
import pytest
from pathlib import Path
from watcher.events import FileEvent
from watcher.debounce import debounce, DebounceHandler


class TestFileEvent:
    """Test FileEvent model."""
    
    def test_create_event(self):
        """Test creating a file event."""
        event = FileEvent(path="/test/file.txt", type="created")
        
        assert event.path == "/test/file.txt"
        assert event.type == "created"


class TestDebounce:
    """Test debounce functionality."""
    
    def test_debounce_empty_list(self):
        """Test debouncing empty event list."""
        result = debounce([])
        assert result == []
    
    def test_debounce_single_event(self):
        """Test debouncing single event."""
        events = [FileEvent(path="/test/file.txt", type="created")]
        result = debounce(events)
        
        assert len(result) == 1
        assert result[0].path == "/test/file.txt"
    
    def test_debounce_multiple_paths(self):
        """Test debouncing events for different paths."""
        events = [
            FileEvent(path="/test/file1.txt", type="created"),
            FileEvent(path="/test/file2.txt", type="created"),
            FileEvent(path="/test/file3.txt", type="modified"),
        ]
        result = debounce(events)
        
        assert len(result) == 3
    
    def test_debounce_same_path(self):
        """Test debouncing multiple events for same path."""
        events = [
            FileEvent(path="/test/file.txt", type="created"),
            FileEvent(path="/test/file.txt", type="modified"),
            FileEvent(path="/test/file.txt", type="modified"),
        ]
        result = debounce(events)
        
        # Should keep only the last event for the path
        assert len(result) == 1
        assert result[0].type == "modified"


class TestDebounceHandler:
    """Test DebounceHandler class."""
    
    def test_debounce_handler_creation(self):
        """Test creating a debounce handler."""
        called = []
        
        def callback(event):
            called.append(event)
        
        handler = DebounceHandler(delay=0.1, callback=callback)
        assert handler.delay == 0.1
        assert handler.callback == callback
    
    def test_debounce_handler_fires(self):
        """Test that debounce handler fires after delay."""
        called = []
        
        def callback(event):
            called.append(event.path)
        
        handler = DebounceHandler(delay=0.1, callback=callback)
        handler.add_event(FileEvent(path="/test/file.txt", type="created"))
        
        # Should not fire immediately
        assert len(called) == 0
        
        # Wait for debounce delay
        time.sleep(0.2)
        
        # Should have fired
        assert len(called) == 1
        assert called[0] == "/test/file.txt"
    
    def test_debounce_handler_multiple_events(self):
        """Test debounce handler with multiple events for same path."""
        called = []
        
        def callback(event):
            called.append(event.type)
        
        handler = DebounceHandler(delay=0.1, callback=callback)
        
        # Add multiple events quickly
        handler.add_event(FileEvent(path="/test/file.txt", type="created"))
        time.sleep(0.05)
        handler.add_event(FileEvent(path="/test/file.txt", type="modified"))
        
        # Wait for debounce delay
        time.sleep(0.15)
        
        # Should only fire once with the last event
        assert len(called) == 1
        assert called[0] == "modified"
    
    def test_debounce_handler_different_paths(self):
        """Test debounce handler with events for different paths."""
        called = []
        
        def callback(event):
            called.append(event.path)
        
        handler = DebounceHandler(delay=0.1, callback=callback)
        
        handler.add_event(FileEvent(path="/test/file1.txt", type="created"))
        handler.add_event(FileEvent(path="/test/file2.txt", type="created"))
        
        # Wait for debounce delay
        time.sleep(0.2)
        
        # Both should fire
        assert len(called) == 2
        assert set(called) == {"/test/file1.txt", "/test/file2.txt"}
    
    def test_debounce_handler_flush(self):
        """Test flushing pending events immediately."""
        called = []
        
        def callback(event):
            called.append(event.path)
        
        handler = DebounceHandler(delay=1.0, callback=callback)
        
        handler.add_event(FileEvent(path="/test/file.txt", type="created"))
        
        # Flush immediately
        handler.flush()
        
        # Should fire immediately without waiting for delay
        assert len(called) == 1
    
    def test_debounce_handler_error_handling(self):
        """Test that handler errors are caught and logged."""
        def failing_callback(event):
            raise ValueError("Test error")
        
        handler = DebounceHandler(delay=0.1, callback=failing_callback)
        
        # Should not raise exception
        handler.add_event(FileEvent(path="/test/file.txt", type="created"))
        time.sleep(0.2)
        
        # Test passes if no exception was raised
