"""In-memory peak tracker + TSV export."""
import statistics
from collections import deque
from pathlib import Path
from datetime import datetime
from segments import SEGMENTS, SOURCES


class PeakStore:
    # Anti-spike layered defense for noisy OCR reads:
    #   1. Buffer of 7 samples, peak update gated on median.
    #   2. Agreement check: median accepted only if >=5 of 7 reads fall within
    #      ±5% of it. Filters bursts where OCR misreads the same digit twice.
    #   3. Spike guard: a confirmed value >1.3× current peak must persist as
    #      the consistent median across 3 consecutive update cycles before
    #      being applied. Real viewer counts climb smoothly; OCR jumps don't.
    BUFFER_SIZE = 7
    AGREEMENT_TOL = 0.05
    MIN_AGREE = 5
    SPIKE_RATIO = 1.3
    SPIKE_CONFIRMS = 3

    def __init__(self):
        # {segment: {label: int}}
        self.peaks = {seg: {src: 0 for src in SOURCES} for seg in SEGMENTS}
        # Per-source rolling buffer of recent OCR reads (shared across segments —
        # the OCR sees the same on-screen counters regardless of which segment is selected).
        self.recent = {src: deque(maxlen=self.BUFFER_SIZE) for src in SOURCES}
        # Per-(segment,source) candidate awaiting spike confirmation.
        # Entry: {"value": int, "count": int} or None.
        self._pending = {seg: {src: None for src in SOURCES} for seg in SEGMENTS}

    def update(self, segment: str, label: str, value):
        if value is None or value <= 0:
            return
        # Guard: segment may be mid-removal by the editor while capture thread runs.
        if segment not in self.peaks or label not in self.recent:
            return
        buf = self.recent[label]
        buf.append(value)
        if len(buf) < self.BUFFER_SIZE:
            return

        confirmed = int(statistics.median(buf))
        if confirmed <= 0:
            return

        tol = confirmed * self.AGREEMENT_TOL
        agree = sum(1 for v in buf if abs(v - confirmed) <= tol)
        if agree < self.MIN_AGREE:
            self._pending[segment][label] = None
            return

        current_peak = self.peaks[segment][label]
        if confirmed <= current_peak:
            self._pending[segment][label] = None
            return

        # Spike guard: large jumps must repeat across SPIKE_CONFIRMS cycles.
        if current_peak > 0 and confirmed > current_peak * self.SPIKE_RATIO:
            pending = self._pending[segment][label]
            if pending is not None and abs(confirmed - pending["value"]) <= pending["value"] * self.AGREEMENT_TOL:
                pending["count"] += 1
                if pending["count"] >= self.SPIKE_CONFIRMS:
                    self.peaks[segment][label] = confirmed
                    self._pending[segment][label] = None
            else:
                self._pending[segment][label] = {"value": confirmed, "count": 1}
            return

        self.peaks[segment][label] = confirmed
        self._pending[segment][label] = None

    def get_current(self, segment: str) -> dict:
        return dict(self.peaks[segment])

    def reset_segment(self, segment: str):
        if segment in self.peaks:
            self.peaks[segment] = {src: 0 for src in SOURCES}
            self._pending[segment] = {src: None for src in SOURCES}

    def reconfigure_segments(self, new_segments: list, rename_map: dict | None = None):
        """Reshape segment-keyed structures to match new_segments.
        rename_map: {old_segment: new_segment} — preserves peak/pending state
        across renames. Removed segments are dropped; brand-new segments start at 0.
        """
        rename_map = rename_map or {}
        inv = {new: old for old, new in rename_map.items()}
        sources = list(next(iter(self.peaks.values())).keys()) if self.peaks else []

        new_peaks = {}
        new_pending = {}
        for seg in new_segments:
            old = inv.get(seg, seg)
            if old in self.peaks:
                new_peaks[seg] = dict(self.peaks[old])
                new_pending[seg] = dict(self._pending[old])
            else:
                new_peaks[seg] = {src: 0 for src in sources}
                new_pending[seg] = {src: None for src in sources}
        self.peaks = new_peaks
        self._pending = new_pending

    def reconfigure_sources(self, new_sources: list, rename_map: dict | None = None):
        """Reshape internal source-keyed structures to match new_sources.
        rename_map: {old_label: new_label} — preserves recent/peak/pending state
        across renames. Removed sources are dropped; brand-new sources start at 0.
        """
        rename_map = rename_map or {}
        inv = {new: old for old, new in rename_map.items()}

        new_recent = {}
        for src in new_sources:
            old = inv.get(src, src)
            new_recent[src] = self.recent[old] if old in self.recent else deque(maxlen=self.BUFFER_SIZE)
        self.recent = new_recent

        for seg in self.peaks:
            old_peaks = self.peaks[seg]
            self.peaks[seg] = {src: old_peaks.get(inv.get(src, src), 0) for src in new_sources}
            self._pending[seg] = {src: None for src in new_sources}

    def _build_tsv(self) -> str:
        lines = ["Segmen\t" + "\t".join(SOURCES) + "\tTOTAL"]
        for seg in SEGMENTS:
            vals = [self.peaks[seg][src] for src in SOURCES]
            total = sum(vals)
            row = [seg] + [str(v) for v in vals] + [str(total)]
            lines.append("\t".join(row))
        return "\n".join(lines)

    def export_to_path(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._build_tsv(), encoding="utf-8")
        return path

    def export_txt(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        path = output_dir / f"peak_{stamp}.txt"
        return self.export_to_path(path)
