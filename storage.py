"""In-memory peak tracker + TSV export."""
from pathlib import Path
from datetime import datetime
from segments import SEGMENTS, SOURCES


class PeakStore:
    def __init__(self):
        # {segment: {label: int}}
        self.peaks = {seg: {src: 0 for src in SOURCES} for seg in SEGMENTS}

    def update(self, segment: str, label: str, value):
        if value is None or value <= 0:
            return
        if value > self.peaks[segment][label]:
            self.peaks[segment][label] = value

    def get_current(self, segment: str) -> dict:
        return dict(self.peaks[segment])

    def reset_segment(self, segment: str):
        if segment in self.peaks:
            self.peaks[segment] = {src: 0 for src in SOURCES}

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
