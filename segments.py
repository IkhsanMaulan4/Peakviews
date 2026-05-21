"""Source list + segment list (both file-backed, editable at runtime)."""
import json

from paths import app_dir

DEFAULT_SOURCES = ["BOG-YT", "MPL-YT", "MDL-YT", "DG-YT", "BYu-YT"]
_SOURCES_FILE = app_dir() / "sources.json"
_SEGMENTS_FILE = app_dir() / "segments.json"


def load_sources() -> list[str]:
    """Read source labels from sources.json; fall back to defaults if missing/invalid."""
    if _SOURCES_FILE.exists():
        try:
            data = json.loads(_SOURCES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data and all(isinstance(x, str) and x.strip() for x in data):
                return [x.strip() for x in data]
        except Exception:
            pass
    return list(DEFAULT_SOURCES)


def save_sources(sources: list[str]) -> None:
    _SOURCES_FILE.write_text(json.dumps(sources, indent=2), encoding="utf-8")


def reload_sources() -> None:
    """Refresh SOURCES in-place so callers holding a reference see the new list."""
    SOURCES[:] = load_sources()


def _build_default_segments():
    intro = ["Waiting Screen", "TVC", "Opening Caster", "Trivia"]
    matches = []
    for m in range(1, 4):
        for g in range(1, 4):
            for phase in ["Pre Game", "In Game", "Post Game"]:
                matches.append(f"Match {m} - Game #{g} {phase}")
    return intro + matches


def load_segments() -> list[str]:
    """Read segment list from segments.json; fall back to BO3 default if missing/invalid."""
    if _SEGMENTS_FILE.exists():
        try:
            data = json.loads(_SEGMENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data and all(isinstance(x, str) and x.strip() for x in data):
                return [x.strip() for x in data]
        except Exception:
            pass
    return _build_default_segments()


def save_segments(segments: list[str]) -> None:
    _SEGMENTS_FILE.write_text(json.dumps(segments, indent=2), encoding="utf-8")


def reload_segments() -> None:
    """Refresh SEGMENTS in-place so callers holding a reference see the new list."""
    SEGMENTS[:] = load_segments()


# Mutable lists — mutate via reload_*() so existing imports stay valid.
SOURCES = load_sources()
SEGMENTS = load_segments()
