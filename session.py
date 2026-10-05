"""Active-segment state shared by the Tk GUI, the capture thread and the web server.

No tkinter here: subscribers are plain callables, and GUI subscribers are
responsible for hopping onto the Tk thread (root.after) themselves.
"""
import threading


class SessionState:
    def __init__(self, segments: list):
        # Live reference to segments.SEGMENTS (mutated in place by the editor).
        self._segments = segments
        self._lock = threading.RLock()  # reentrant: subscribers may read state
        self._index = 0
        self._subscribers = []

    @property
    def index(self) -> int:
        with self._lock:
            return self._clamped()

    def current_name(self):
        with self._lock:
            return self._name_at(self._clamped())

    def subscribe(self, callback) -> None:
        """callback(index, name) runs on the thread that changed the segment."""
        with self._lock:
            self._subscribers.append(callback)

    def set_index(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self._segments):
                return False
            return self._apply(index)

    def set_by_name(self, name: str) -> bool:
        with self._lock:
            try:
                index = self._segments.index(name)
            except ValueError:
                return False
            return self._apply(index)

    def next(self) -> bool:
        with self._lock:
            return self._step(1)

    def prev(self) -> bool:
        with self._lock:
            return self._step(-1)

    def sync_to(self, name) -> None:
        """Re-point at `name` after the segment list was edited in place.

        Silent: the editing code already re-renders, so subscribers are not fired.
        Falls back to a clamped index when the name no longer exists.
        """
        with self._lock:
            if name in self._segments:
                self._index = self._segments.index(name)
            else:
                self._index = self._clamped()

    # --- internals (caller holds the lock) -----------------------------

    def _clamped(self) -> int:
        if not self._segments:
            return 0
        return min(self._index, len(self._segments) - 1)

    def _name_at(self, index: int):
        return self._segments[index] if self._segments else None

    def _step(self, delta: int) -> bool:
        target = self._clamped() + delta
        if not 0 <= target < len(self._segments):
            return False
        return self._apply(target)

    def _apply(self, index: int) -> bool:
        if index == self._clamped():
            return False
        self._index = index
        name = self._segments[index]
        subscribers = list(self._subscribers)
        # Notified under the (reentrant) lock so listeners see changes in order.
        self._notify(subscribers, index, name)
        return True

    @staticmethod
    def _notify(subscribers, index, name) -> None:
        for callback in subscribers:
            try:
                callback(index, name)
            except Exception:
                pass  # a broken listener must never block a segment change
