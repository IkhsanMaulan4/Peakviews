import web_api
from tests.webfixtures import make_context, warm


def test_group_name_splits_on_dash():
    assert web_api.group_of("Match 1 - Game #1 In Game") == "Match 1"
    assert web_api.group_of("TVC") == "Umum"


def test_state_shape(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    warm(ctx)
    s = web_api.build_state(ctx)
    assert s["segment"] == "Waiting Screen"
    assert s["index"] == 0 and s["total"] == 4
    assert s["running"] is True
    assert s["sources"] == ["AAA-YT", "BBB-YT"]
    assert s["viewers"] == {"AAA-YT": 1000, "BBB-YT": 2000}
    assert s["peaks"] == {"AAA-YT": 1000, "BBB-YT": 2000}
    assert s["health"] == {"AAA-YT": "ok", "BBB-YT": "ok"}
    assert s["segments"][2] == {"name": "Match 1 - Game #1 In Game", "group": "Match 1"}


def test_state_reflects_segment_change(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    ctx.session.next()
    assert web_api.build_state(ctx)["segment"] == "TVC"


def test_state_with_no_data_has_none_viewers(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    s = web_api.build_state(ctx)
    assert s["viewers"] == {"AAA-YT": None, "BBB-YT": None}
    assert s["peaks"] == {"AAA-YT": 0, "BBB-YT": 0}


def test_summary_skips_empty_segments_and_totals(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    warm(ctx, 1000, 2000)
    sm = web_api.build_summary(ctx)
    assert [r["name"] for r in sm["segments"]] == ["Waiting Screen"]
    assert sm["segments"][0]["peaks"] == {"AAA-YT": 1000, "BBB-YT": 2000}
    assert sm["segments"][0]["total"] == 3000


def test_timeline_delta(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    warm(ctx)
    first = web_api.build_timeline(ctx, 0)
    assert first["sources"] == ["AAA-YT", "BBB-YT"]
    assert len(first["points"]) == 8
    again = web_api.build_timeline(ctx, first["next"])
    assert again["points"] == []


def test_apply_segment_by_name(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    assert web_api.apply_segment(ctx, {"name": "TVC"}) == (True, True)
    assert ctx.session.current_name() == "TVC"


def test_apply_segment_actions(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    assert web_api.apply_segment(ctx, {"action": "next"}) == (True, True)
    assert web_api.apply_segment(ctx, {"action": "prev"}) == (True, True)
    assert web_api.apply_segment(ctx, {"action": "prev"}) == (True, False)  # at start


def test_apply_segment_rejects_bad_input(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    for body in ({"name": "nope"}, {"name": 5}, {"action": "jump"}, {}, [], "x", None):
        valid, _ = web_api.apply_segment(ctx, body)
        assert valid is False
    assert ctx.session.index == 0


def test_summary_tolerates_segments_missing_from_store(tmp_path, monkeypatch):
    """SEGMENTS is swapped before the store is reshaped during a segment edit."""
    ctx = make_context(tmp_path, monkeypatch)
    warm(ctx)
    ctx.segments.append("Brand New")
    sm = web_api.build_summary(ctx)
    assert [r["name"] for r in sm["segments"]] == ["Waiting Screen"]


def test_state_index_and_name_agree(tmp_path, monkeypatch):
    ctx = make_context(tmp_path, monkeypatch)
    ctx.session.set_index(2)
    s = web_api.build_state(ctx)
    assert s["segments"][s["index"]]["name"] == s["segment"]
