import threading

from storage import PeakStore
import segments


def _feed(store, seg, src, value, n=7):
    for _ in range(n):
        store.update(seg, src, value)


def test_snapshot_is_a_deep_copy():
    store = PeakStore()
    seg, src = segments.SEGMENTS[0], segments.SOURCES[0]
    _feed(store, seg, src, 1000)
    snap = store.snapshot()
    assert snap[seg][src] == 1000
    snap[seg][src] = 5
    assert store.peaks[seg][src] == 1000


def test_snapshot_covers_every_segment_and_source():
    snap = PeakStore().snapshot()
    assert list(snap) == list(segments.SEGMENTS)
    assert all(list(v) == list(segments.SOURCES) for v in snap.values())


def test_snapshot_safe_during_concurrent_writes_and_reconfigure():
    store = PeakStore()
    seg, src = segments.SEGMENTS[0], segments.SOURCES[0]
    errors = []
    stop = threading.Event()

    def writer():
        v = 1000
        while not stop.is_set():
            v += 1
            store.update(seg, src, v)

    def reshaper():
        names = list(segments.SEGMENTS)
        while not stop.is_set():
            store.reconfigure_segments(list(reversed(names)))
            store.reconfigure_segments(names)

    def reader():
        try:
            for _ in range(500):
                store.snapshot()
        except Exception as e:  # dict changed size during iteration etc.
            errors.append(e)

    threads = [threading.Thread(target=f) for f in (writer, reshaper)]
    for t in threads:
        t.start()
    reader()
    stop.set()
    for t in threads:
        t.join()
    assert errors == []
