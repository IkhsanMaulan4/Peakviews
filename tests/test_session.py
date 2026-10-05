import threading

import pytest

from session import SessionState


@pytest.fixture
def segs():
    return ["A", "B", "C"]


@pytest.fixture
def state(segs):
    return SessionState(segs)


def test_starts_at_first_segment(state):
    assert state.index == 0
    assert state.current_name() == "A"


def test_next_advances_and_reports_change(state):
    assert state.next() is True
    assert state.current_name() == "B"


def test_next_at_end_is_noop(state):
    state.set_index(2)
    assert state.next() is False
    assert state.index == 2


def test_prev_at_start_is_noop(state):
    assert state.prev() is False
    assert state.index == 0


def test_set_by_name_valid(state):
    assert state.set_by_name("C") is True
    assert state.index == 2


def test_set_by_name_unknown_rejected(state):
    assert state.set_by_name("nope") is False
    assert state.index == 0


def test_set_index_out_of_range_rejected(state):
    assert state.set_index(5) is False
    assert state.set_index(-1) is False
    assert state.index == 0


def test_setting_same_segment_reports_no_change(state):
    assert state.set_by_name("A") is False


def test_subscriber_called_on_change_only(state):
    seen = []
    state.subscribe(lambda idx, name: seen.append((idx, name)))
    state.next()
    state.next()
    state.set_by_name("C")  # already there
    state.prev()
    assert seen == [(1, "B"), (2, "C"), (1, "B")]


def test_subscriber_exception_does_not_break_state(state):
    def boom(idx, name):
        raise RuntimeError("x")

    state.subscribe(boom)
    assert state.next() is True
    assert state.index == 1


def test_follows_live_list_mutation(segs, state):
    state.set_index(2)
    segs[:] = ["A", "B"]  # segment editor shrank the list in place
    assert state.index == 1
    assert state.current_name() == "B"


def test_empty_list_is_safe():
    s = SessionState([])
    assert s.index == 0
    assert s.current_name() is None
    assert s.next() is False


def test_replace_keeps_segment_by_name(segs, state):
    state.set_by_name("C")
    segs[:] = ["X", "C", "A"]
    state.sync_to("C")
    assert state.current_name() == "C"
    assert state.index == 1


def test_concurrent_next_never_exceeds_bounds():
    s = SessionState([str(i) for i in range(50)])

    def spam():
        for _ in range(200):
            s.next()
            s.prev()
            s.next()

    threads = [threading.Thread(target=spam) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert 0 <= s.index < 50


def test_subscriber_may_read_state_without_deadlock(state):
    seen = []
    state.subscribe(lambda idx, name: seen.append(state.index))
    state.next()
    assert seen == [1]


def test_subscriber_runs_outside_the_lock(state):
    """A subscriber that waits on another thread reading state must not deadlock
    (the real app's subscriber blocks on Tk's main thread, which reads state)."""
    done = []

    def sub(idx, name):
        reader = threading.Thread(target=lambda: done.append(state.index))
        reader.start()
        reader.join(timeout=2)

    state.subscribe(sub)
    state.next()
    assert done == [1]


def test_snapshot_returns_consistent_index_and_name(state):
    state.set_index(2)
    assert state.snapshot() == (2, "C")


def test_snapshot_empty_list():
    assert SessionState([]).snapshot() == (0, None)


def test_apply_edit_mutates_and_resyncs_atomically(segs, state):
    state.set_by_name("C")

    def mutate():
        segs[:] = ["X", "C", "A"]

    state.apply_edit(mutate, "C")
    assert state.snapshot() == (1, "C")


def test_apply_edit_falls_back_to_clamped_index(segs, state):
    state.set_index(2)
    state.apply_edit(lambda: segs.__setitem__(slice(None), ["A"]), "gone")
    assert state.snapshot() == (0, "A")
