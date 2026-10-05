"""Cleaned time-series log + per-source OCR health, independent of tkinter.

The cleaning mirrors PeakStore's anti-spike layers (median buffer, agreement
check, spike guard) but is two-sided: viewer counts legitimately fall, so a
large drop must also persist across several cycles before it is accepted.
"""
import csv
import statistics
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

BUFFER_SIZE = 7
AGREEMENT_TOL = 0.05
MIN_AGREE = 5
SPIKE_RATIO = 1.3
SPIKE_CONFIRMS = 3

LOG_INTERVAL = 5.0   # seconds between CSV rows
WARN_AFTER = 5.0     # seconds without a valid read -> yellow
ERROR_AFTER = 15.0   # seconds without a valid read -> red
HISTORY_MAX = 4000   # in-memory points for the live chart (~5.5h at LOG_INTERVAL)

FLAG_OK = "ok"
FLAG_HELD = "held"   # raw read rejected, last accepted value reused
FLAG_GAP = "gap"     # no accepted value exists yet

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_ERROR = "error"


class SeriesCleaner:
    """Turns noisy per-cycle OCR reads of one source into accepted values."""

    def __init__(self):
        self._buffer = deque(maxlen=BUFFER_SIZE)
        self._last = None
        self._pending = None  # {"value": int, "count": int}

    @property
    def last(self):
        """Last accepted (cleaned) value, or None before the buffer has warmed up."""
        return self._last

    def push(self, value):
        """Returns (accepted_value_or_None, flag)."""
        if value is not None and value > 0:
            self._buffer.append(value)
        if len(self._buffer) < BUFFER_SIZE:
            return self._held()

        confirmed = int(statistics.median(self._buffer))
        tol = confirmed * AGREEMENT_TOL
        agree = sum(1 for v in self._buffer if abs(v - confirmed) <= tol)
        if confirmed <= 0 or agree < MIN_AGREE:
            self._pending = None
            return self._held()

        last = self._last
        if last is not None and (confirmed > last * SPIKE_RATIO or confirmed < last / SPIKE_RATIO):
            return self._confirm_jump(confirmed)

        self._pending = None
        self._last = confirmed
        return confirmed, FLAG_OK

    def _confirm_jump(self, confirmed):
        pending = self._pending
        if pending is not None and abs(confirmed - pending["value"]) <= pending["value"] * AGREEMENT_TOL:
            pending["count"] += 1
            if pending["count"] >= SPIKE_CONFIRMS:
                self._pending = None
                self._last = confirmed
                return confirmed, FLAG_OK
        else:
            self._pending = {"value": confirmed, "count": 1}
        return self._held()

    def _held(self):
        if self._last is None:
            return None, FLAG_GAP
        return self._last, FLAG_HELD


class TimelineTracker:
    """Cleans reads, writes a CSV row every LOG_INTERVAL, tracks OCR health.

    feed() runs on the capture thread, status()/set_sources() on the GUI
    thread, so shared state is guarded by a lock.
    """

    def __init__(self, output_dir: Path, stamp: str, sources: list):
        self._output_dir = output_dir
        self._stamp = stamp
        self._lock = threading.Lock()
        self._file_count = 0
        self._path = None
        self._needs_header = False
        self._last_write = 0.0
        self._history = deque(maxlen=HISTORY_MAX)
        self._next_seq = 0
        self._set_sources_locked(sources, time.monotonic())

    @property
    def path(self):
        return self._path

    def set_sources(self, sources: list):
        with self._lock:
            self._set_sources_locked(sources, time.monotonic())

    def _set_sources_locked(self, sources, now):
        self._sources = list(sources)
        self._cleaners = {src: SeriesCleaner() for src in self._sources}
        self._last_ok = {src: now for src in self._sources}
        self._path = None  # next write opens a fresh file with a matching header
        self._history.clear()

    def feed(self, segment: str, raw: dict):
        mono = time.monotonic()
        with self._lock:
            readings = {}
            for src in self._sources:
                value = raw.get(src)
                if value is not None and value > 0:
                    self._last_ok[src] = mono
                readings[src] = self._cleaners[src].push(value)
            if mono - self._last_write >= LOG_INTERVAL:
                self._last_write = mono
                self._record_history(segment, readings)
                self._write_row(segment, readings)

    def latest(self) -> dict:
        """{source: cleaned viewer count or None} - anti-spike filtered, not raw OCR."""
        with self._lock:
            return {src: self._cleaners[src].last for src in self._sources}

    def statuses(self) -> dict:
        with self._lock:
            now = time.monotonic()
            return {src: self._status_at(self._last_ok.get(src), now) for src in self._sources}

    def history(self, since: int = 0):
        """Points with seq >= since, plus the seq to pass next time."""
        with self._lock:
            points = [p for p in self._history if p["seq"] >= since]
            return points, self._next_seq

    def _record_history(self, segment, readings):
        self._history.append({
            "seq": self._next_seq,
            "t": time.time(),
            "segment": segment,
            "values": {src: readings[src][0] for src in self._sources},
        })
        self._next_seq += 1

    def status(self, src: str) -> str:
        with self._lock:
            last_ok = self._last_ok.get(src)
        return self._status_at(last_ok, time.monotonic())

    @staticmethod
    def _status_at(last_ok, now) -> str:
        if last_ok is None:
            return STATUS_OK
        silent = now - last_ok
        if silent >= ERROR_AFTER:
            return STATUS_ERROR
        if silent >= WARN_AFTER:
            return STATUS_WARN
        return STATUS_OK

    def _write_row(self, segment, readings):
        if not self._sources:
            return
        if self._path is None:
            suffix = "" if self._file_count == 0 else f"_{self._file_count + 1}"
            self._path = self._output_dir / f"timeline_{self._stamp}{suffix}.csv"
            self._file_count += 1
            self._needs_header = True
        flags = ";".join(f"{src}:{flag}" for src, (_, flag) in readings.items() if flag != FLAG_OK)
        row = [datetime.now().isoformat(timespec="seconds"), segment]
        row += ["" if readings[src][0] is None else readings[src][0] for src in self._sources]
        row.append(flags)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if self._needs_header:
                    writer.writerow(["timestamp", "segment", *self._sources, "flags"])
                    self._needs_header = False
                writer.writerow(row)
        except OSError:
            pass  # disk/permission hiccup: skip this row, retry next interval
