"""Shared builders for web tests (no tkinter, no OCR)."""
from pathlib import Path

import timeline
from session import SessionState
from storage import PeakStore
from timeline import TimelineTracker
from web_api import WebContext

SEGMENTS = ["Waiting Screen", "TVC", "Match 1 - Game #1 In Game", "Match 2 - Game #1 In Game"]
SOURCES = ["AAA-YT", "BBB-YT"]


def make_context(tmp_path, monkeypatch, report_builder=None):
    monkeypatch.setattr(timeline, "LOG_INTERVAL", 0.0)
    segments = list(SEGMENTS)
    store = PeakStore()
    store.reconfigure_segments(segments)
    store.reconfigure_sources(list(SOURCES))
    tracker = TimelineTracker(Path(tmp_path), "t", list(SOURCES))
    return WebContext(
        session=SessionState(segments),
        store=store,
        timeline=tracker,
        segments=segments,
        sources=list(SOURCES),
        is_running=lambda: True,
        report_builder=report_builder,
    )


def warm(ctx, a=1000, b=2000, n=8):
    for _ in range(n):
        seg = ctx.session.current_name()
        ctx.timeline.feed(seg, {"AAA-YT": a, "BBB-YT": b})
        ctx.store.update(seg, "AAA-YT", a)
        ctx.store.update(seg, "BBB-YT", b)
