"""JSON payload builders for the local web UI. Pure functions, no tkinter, no HTTP."""
from dataclasses import dataclass, field
from typing import Callable, Optional

from report import _nonempty_segments, _segment_total

DEFAULT_GROUP = "Umum"


@dataclass
class WebContext:
    """Everything the web layer may read, plus the one thing it may change."""
    session: object                      # SessionState
    store: object                        # PeakStore
    timeline: object                     # TimelineTracker
    segments: list                       # live reference to segments.SEGMENTS
    sources: list                        # active source labels
    is_running: Callable[[], bool] = field(default=lambda: True)
    report_builder: Optional[Callable] = None   # () -> Path, may raise NoDataError


def group_of(name: str) -> str:
    """'Match 1 - Game #1 In Game' -> 'Match 1'; names without ' - ' -> 'Umum'."""
    head, sep, _ = name.partition(" - ")
    return head.strip() if sep and head.strip() else DEFAULT_GROUP


def build_state(ctx: WebContext) -> dict:
    segments = list(ctx.segments)
    index = ctx.session.index
    name = ctx.session.current_name()
    peaks = ctx.store.snapshot().get(name, {})
    viewers = ctx.timeline.latest()
    health = ctx.timeline.statuses()
    return {
        "segment": name,
        "index": index,
        "total": len(segments),
        "segments": [{"name": s, "group": group_of(s)} for s in segments],
        "sources": list(ctx.sources),
        "viewers": {src: viewers.get(src) for src in ctx.sources},
        "peaks": {src: peaks.get(src, 0) for src in ctx.sources},
        "health": {src: health.get(src, "ok") for src in ctx.sources},
        "running": bool(ctx.is_running()),
    }


def build_summary(ctx: WebContext) -> dict:
    peaks = ctx.store.snapshot()
    sources = list(ctx.sources)
    rows = []
    for seg in _nonempty_segments(peaks, sources, list(ctx.segments)):
        rows.append({
            "name": seg,
            "peaks": {src: peaks[seg].get(src, 0) for src in sources},
            "total": _segment_total(peaks, sources, seg),
        })
    return {"sources": sources, "segments": rows}


def build_timeline(ctx: WebContext, since: int) -> dict:
    points, nxt = ctx.timeline.history(since)
    return {"sources": list(ctx.sources), "points": points, "next": nxt}


def apply_segment(ctx: WebContext, body) -> tuple:
    """Returns (valid, changed). Only names present in the segment list are accepted."""
    if not isinstance(body, dict):
        return False, False
    name = body.get("name")
    action = body.get("action")
    if isinstance(name, str):
        if name not in ctx.segments:
            return False, False
        return True, ctx.session.set_by_name(name)
    if action == "next":
        return True, ctx.session.next()
    if action == "prev":
        return True, ctx.session.prev()
    return False, False
