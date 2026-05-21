"""Screenshot regions and OCR them into integer peak viewer counts (RapidOCR backend)."""
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import mss
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


# Lazy global engine: first init loads ONNX models (~1-2s). A lock guards init
# AND inference — onnxruntime sessions are generally thread-safe but RapidOCR
# wraps internal state, so we serialize calls for correctness over throughput.
_ENGINE_LOCK = threading.Lock()
_ENGINE: RapidOCR | None = None


def _engine() -> RapidOCR:
    """Init RapidOCR with detection + angle-classifier disabled. The calibrated
    regions are already tight digit crops, so running detection is just a 1+ s
    overhead per frame; rec-only on the whole crop completes in ~6-10 ms.
    """
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = RapidOCR(use_text_det=False, use_angle_cls=False)
    return _ENGINE


# Match number tokens like: 1234, 1,234, 1.2K, 1.5M, 2 jt, 850 rb
_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*\s*(?:[KMkm]|[Jj][Tt]|[Rr][Bb])?")
_SUFFIX_MULT = {"k": 1_000, "rb": 1_000, "m": 1_000_000, "jt": 1_000_000}


def normalize_number(text: str):
    """Parse OCR output like '1.2K', '1,234', '1.5M', '2 jt', '850 rb' into int."""
    if not text:
        return None
    s = text.strip().lower().replace(" ", "")
    if not s:
        return None

    mult = 1
    for suffix in ("jt", "rb"):
        if s.endswith(suffix):
            mult = _SUFFIX_MULT[suffix]
            s = s[: -len(suffix)]
            break
    else:
        if s.endswith("k"):
            mult = _SUFFIX_MULT["k"]
            s = s[:-1]
        elif s.endswith("m"):
            mult = _SUFFIX_MULT["m"]
            s = s[:-1]

    if mult > 1:
        s = s.replace(",", ".")
        try:
            return int(float(s) * mult)
        except ValueError:
            return None
    else:
        s = re.sub(r"[.,]", "", s)
        if not s.isdigit():
            return None
        try:
            return int(s)
        except ValueError:
            return None


def _extract_numbers(text: str):
    for tok in _NUMBER_PATTERN.findall(text):
        val = normalize_number(tok)
        if val is not None and val > 0:
            yield val


def _ocr_image_core(img: Image.Image):
    """Run RapidOCR on a PIL crop, parse numeric tokens from each detected line.
    Returns (final_value, votes_counter, confidence_sum, image_used).
    Multiple detected lines vote; ties broken by aggregate confidence.
    """
    arr = np.array(img.convert("RGB"))
    engine = _engine()  # init outside the inference lock; _engine() does its own DCL.
    try:
        with _ENGINE_LOCK:
            results, _elapsed = engine(arr)
    except Exception:
        results = None

    votes: Counter = Counter()
    confidence_sum: dict[int, float] = {}
    if results:
        for det in results:
            text = det[1]
            try:
                conf = float(det[2]) * 100.0  # RapidOCR returns 0..1 strings
            except (ValueError, TypeError):
                conf = 0.0
            for val in _extract_numbers(text):
                votes[val] += 1
                confidence_sum[val] = confidence_sum.get(val, 0.0) + conf

    if not votes:
        return None, votes, confidence_sum, img
    ranked = sorted(
        votes.items(),
        key=lambda kv: (kv[1], confidence_sum.get(kv[0], 0.0)),
        reverse=True,
    )
    return ranked[0][0], votes, confidence_sum, img


def _ocr_image(img: Image.Image):
    value, _, _, _ = _ocr_image_core(img)
    return value


def _grab(sct, region) -> Image.Image:
    x, y, w, h = region
    bbox = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
    raw = sct.grab(bbox)
    return Image.frombytes("RGB", raw.size, raw.rgb)


def capture_all(regions: dict) -> dict:
    """regions: {label: [x,y,w,h]} -> {label: int|None}.

    Screenshots are grabbed sequentially (mss isn't thread-safe), OCR runs in
    parallel — the per-call lock inside _ocr_image_core serializes ORT inference
    while allowing the rest of the pipeline (numpy conv, parsing) to overlap.
    """
    if not regions:
        return {}

    with mss.mss() as sct:
        grabs = {label: _grab(sct, region) for label, region in regions.items()}

    def ocr_one(item):
        label, img = item
        try:
            return label, _ocr_image(img)
        except Exception:
            return label, None

    result = {}
    with ThreadPoolExecutor(max_workers=min(len(grabs), 5)) as ex:
        for label, val in ex.map(ocr_one, grabs.items()):
            result[label] = val
    return result


def capture_all_with_debug(regions: dict) -> dict:
    """Same as capture_all, but returns the captured crop + vote tally per
    source so the debug UI can inspect what RapidOCR saw. Slower (carries PIL
    images back); only use when a debug window is open.

    regions: {label: [x,y,w,h]} ->
        {label: {"value": int|None,
                 "bin": PIL.Image | None,    # the actual color crop fed to OCR
                 "bin_inv": None,            # legacy slot, unused with RapidOCR
                 "votes": Counter,
                 "conf": {value: avg_confidence}}}
    """
    if not regions:
        return {}

    with mss.mss() as sct:
        grabs = {label: _grab(sct, region) for label, region in regions.items()}

    def ocr_one(item):
        label, img = item
        try:
            value, votes, conf_sum, used_img = _ocr_image_core(img)
        except Exception:
            return label, {"value": None, "bin": None, "bin_inv": None, "votes": Counter(), "conf": {}}
        avg_conf = {v: conf_sum[v] / votes[v] for v in votes}
        return label, {
            "value": value,
            "bin": used_img,
            "bin_inv": None,
            "votes": votes,
            "conf": avg_conf,
        }

    result = {}
    with ThreadPoolExecutor(max_workers=min(len(grabs), 5)) as ex:
        for label, payload in ex.map(ocr_one, grabs.items()):
            result[label] = payload
    return result
