"""Active-segment state shared by the Tk GUI, the capture thread and the web server.

No tkinter here: subscribers are plain callables, and GUI subscribers are
responsible for hopping onto the Tk thread (root.after) themselves.

Subscribers run on the calling thread *after* the lock is released. That matters:
a GUI subscriber may block waiting on the Tk main thread, which in turn may be
reading this state - holding the lock across the callback would deadlock.
"""
import threading
from typing import Callable, Optional


class SessionState:
    def __init__(self, segments: list):
        # Live reference to segments.SEGMENTS (mutated in place by the editor).
        self._segments = segments
        self._lock = threading.RLock()
        self._index = 0
        self._subscribers: list = []

    @property
    def index(self) -> int:
        with self._lock:
            return self._clamped()

    def current_name(self) -> Optional[str]:
        with self._lock:
            return self._name_at(self._clamped())

    def snapshot(self) -> tuple:
        """(index, name) read atomically."""
        with self._lock:
            index = self._clamped()
            return index, self._name_at(index)

    def subscribe(self, callback: Callable[[int, str], None]) -> None:
        """callback(index, name) runs on the thread that changed the segment."""
        with self._lock:
            self._subscribers.append(callback)

    def set_index(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self._segments):
                return False
            event = self._apply(index)
        return self._publish(event)

    def set_by_name(self, name: str) -> bool:
        with self._lock:
            try:
                index = self._segments.index(name)
            except ValueError:
                return False
            event = self._apply(index)
        return self._publish(event)

    def next(self) -> bool:
        with self._lock:
            event = self._step(1)
        return self._publish(event)

    def prev(self) -> bool:
        with self._lock:
            event = self._step(-1)
        return self._publish(event)

    def sync_to(self, name) -> None:
        """Re-point at `name` after the segment list was edited in place (silent)."""
        with self._lock:
            self._resync(name)

    def apply_edit(self, mutate: Callable[[], None], keep_name) -> None:
        """Run `mutate` (which rewrites the segment list) and re-point at `keep_name`
        in one critical section, so no thread sees the new list with the old index."""
        with self._lock:
            mutate()
            self._resync(keep_name)

    # --- internals (caller holds the lock unless noted) -----------------

    def _resync(self, name) -> None:
        if name in self._segments:
            self._index = self._segments.index(name)
        else:
            self._index = self._clamped()

    def _clamped(self) -> int:
        if not self._segments:
            return 0
        return min(self._index, len(self._segments) - 1)

    def _name_at(self, index: int) -> Optional[str]:
        return self._segments[index] if self._segments else None

    def _step(self, delta: int):
        target = self._clamped() + delta
        if not 0 <= target < len(self._segments):
            return None
        return self._apply(target)

    def _apply(self, index: int):
        """Returns (subscribers, index, name) when the segment changed, else None."""
        if index == self._clamped():
            return None
        self._index = index
        return list(self._subscribers), index, self._segments[index]

    @staticmethod
    def _publish(event) -> bool:
        """Called WITHOUT the lock held."""
        if event is None:
            return False
        subscribers, index, name = event
        for callback in subscribers:
            try:
                callback(index, name)
            except Exception:
                pass  # a broken listener must never block a segment change
        return True
