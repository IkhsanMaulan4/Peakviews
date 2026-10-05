import timeline
from timeline import TimelineTracker, SeriesCleaner


def _tracker(tmp_path, monkeypatch, sources=("A", "B")):
    monkeypatch.setattr(timeline, "LOG_INTERVAL", 0.0)  # log every feed
    return TimelineTracker(tmp_path, "t", list(sources))


def _warm(tracker, seg, a, b, n=8):
    for _ in range(n):
        tracker.feed(seg, {"A": a, "B": b})


def test_latest_is_none_before_enough_reads(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    t.feed("S1", {"A": 1000, "B": 2000})
    assert t.latest() == {"A": None, "B": None}


def test_latest_returns_cleaned_values(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000)
    assert t.latest() == {"A": 1000, "B": 2000}


def test_latest_ignores_single_spike(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000)
    t.feed("S1", {"A": 9_999_999, "B": 2000})
    assert t.latest()["A"] == 1000


def test_series_cleaner_exposes_last():
    c = SeriesCleaner()
    assert c.last is None
    for _ in range(7):
        c.push(500)
    assert c.last == 500


def test_statuses_covers_all_sources(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    assert set(t.statuses()) == {"A", "B"}


def test_history_records_points_with_segment(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000)
    t.feed("S2", {"A": 1000, "B": 2000})
    points, nxt = t.history(0)
    assert points[-1]["segment"] == "S2"
    assert points[0]["segment"] == "S1"
    assert points[-1]["values"] == {"A": 1000, "B": 2000}
    assert nxt == points[-1]["seq"] + 1


def test_history_since_returns_only_new_points(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000)
    _, nxt = t.history(0)
    t.feed("S1", {"A": 1000, "B": 2000})
    points, nxt2 = t.history(nxt)
    assert len(points) == 1
    assert nxt2 == nxt + 1


def test_history_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(timeline, "HISTORY_MAX", 5)
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000, n=30)
    points, _ = t.history(0)
    assert len(points) == 5


def test_set_sources_clears_history(tmp_path, monkeypatch):
    t = _tracker(tmp_path, monkeypatch)
    _warm(t, "S1", 1000, 2000)
    t.set_sources(["A"])
    points, _ = t.history(0)
    assert points == []
    assert set(t.latest()) == {"A"}
