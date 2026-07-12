import threading
import time


class DownloadControl:
    """Shared pause/resume/stop switch between the dashboard (or CLI) and
    the download loop. The loop checks in between API calls so pausing or
    stopping never happens mid-write."""

    def __init__(self):
        self._stop = threading.Event()
        self._paused = threading.Event()

    def stop(self):
        self._stop.set()
        self._paused.clear()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def reset(self):
        self._stop.clear()
        self._paused.clear()

    def should_stop(self):
        return self._stop.is_set()

    def is_paused(self):
        return self._paused.is_set()

    def wait_if_paused(self):
        while self._paused.is_set() and not self._stop.is_set():
            time.sleep(0.2)
