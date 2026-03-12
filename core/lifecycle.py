"""Lifecycle manager: startup/shutdown and signal handling (stub)."""

import signal
import threading
import time


class LifecycleManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self._stop = threading.Event()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, *args):
        self._stop.set()

    def wait_for_shutdown(self):
        try:
            while not self._stop.is_set():
                time.sleep(0.5)
        finally:
            self.shutdown()

    def shutdown(self):
        # TODO: gracefully stop workers, watcher, DB, etc.
        pass
