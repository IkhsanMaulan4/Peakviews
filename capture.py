"""Screenshot 4 regions and OCR them into integer peak viewer counts."""
import os
import re
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import mss
import pytesseract
from pytesseract import Output
from PIL import Image, ImageFilter, ImageOps
from paths import bundled_tesseract

# Auto-detect Tesseract path: prefer bundled (frozen build), else search system installs
_bundled = bundled_tesseract()
if _bundled is not None:
    pytesseract.pytesseract.tesseract_cmd = str(_bundled)
elif not shutil.which("tesseract"):
    for path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break

_WHITELIST = "0123456789KMkmRrBbJjTt., "
# PSM 8 (single word) + PSM 7 (single line) are the most reliable for tight digit crops.
# Each tesseract call spawns a subprocess (~80-150ms on Windows), so we keep this minimal.
OCR_CONFIGS = [
    f"--psm 8 -c tessedit_char_whitelist={_WHITELIST}",
    f"--psm 7 -c tessedit_char_whitelist={_WHITELIST}",
]

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

    # If has suffix, dot/comma = decimal separator. Otherwise = thousands separator.
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
    """Yield all valid positive ints found in OCR output."""
    for tok in _NUMBER_PATTERN.findall(text):
        val = normalize_number(tok)
        if val is not None and val > 0:
            yield val


def _otsu_threshold(img: Image.Image) -> int:
    """Compute Otsu's threshold for a grayscale PIL image."""
    hist = img.histogram()[:256]
    total = sum(hist)
    if total == 0:
        return 128
    sum_total = sum(i * h for i, h in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    max_var = -1.0
    threshold = 128
    for i in range(256):
        weight_bg += hist[i]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * hist[i]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > max_var:
            max_var = var
            threshold = i
    return threshold


def _binarize(img: Image.Image) -> Image.Image:
    t = _otsu_threshold(img)
    return img.point(lambda p: 255 if p > t else 0).convert("L")


def _preprocess(img: Image.Image):
    """Yield (name, image) variants: binarized + binarized-inverted."""
    # 4x upscale + sharpen makes thin digit strokes much easier for Tesseract
    img = img.convert("L")
    img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=180, threshold=2))
    img = ImageOps.autocontrast(img)

    binar = _binarize(img)
    yield "bin", binar
    yield "bin_inv", ImageOps.invert(binar)


def _reconstruct_text(words: list) -> str:
    """Join tesseract word tokens with bbox-aware spacing: adjacent words
    (small gap) glue together, normal gaps become a space. Prevents over-
    tokenization like ['5,', '613'] from being read as two separate numbers,
    which matters for locales that use '.' or ',' as thousand separators.
    """
    if not words:
        return ""
    lines: dict = {}
    for w in words:
        lines.setdefault(w["line"], []).append(w)
    out = []
    for key in sorted(lines):
        row = sorted(lines[key], key=lambda w: w["left"])
        # avg char width — single-char tokens dominate when tesseract splits punctuation
        avg_char = sum(w["width"] / max(len(w["text"]), 1) for w in row) / len(row)
        glue = avg_char * 0.5
        parts = [row[0]["text"]]
        prev = row[0]
        for w in row[1:]:
            gap = w["left"] - (prev["left"] + prev["width"])
            parts.append(("" if gap < glue else " ") + w["text"])
            prev = w
        out.append("".join(parts))
    return " ".join(out)


def _ocr_call(variant: Image.Image, config: str):
    """Run one tesseract pass. Returns (numbers, avg_conf, digits_in_text).
    avg_conf is the mean of word-level confidences (0-100), ignoring tesseract's
    -1 "no confidence" markers; 0.0 if no scored words.
    """
    try:
        data = pytesseract.image_to_data(variant, config=config, output_type=Output.DICT)
    except Exception:
        return [], 0.0, 0
    words = []
    for i, t in enumerate(data["text"]):
        if not t or not t.strip():
            continue
        # Tesseract 5.x emits conf as fractional ("94.371071"); pytesseract
        # keeps it as a string because '.' fails .isdigit(). Go via float().
        words.append({
            "text": t,
            "conf": float(data["conf"][i]),
            "left": int(float(data["left"][i])),
            "width": int(float(data["width"][i])),
            "line": (
                int(float(data["block_num"][i])),
                int(float(data["par_num"][i])),
                int(float(data["line_num"][i])),
            ),
        })
    confs = [w["conf"] for w in words if w["conf"] >= 0]
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    text = _reconstruct_text(words)
    digits_in_text = sum(1 for ch in text if ch.isdigit())
    return list(_extract_numbers(text)), avg_conf, digits_in_text


def _ocr_image_core(img: Image.Image):
    """Run OCR with multiple preprocessings + PSM modes, vote across readings.
    Tie-break by summed word-confidence so a clean read beats a misread that
    just happened to repeat (e.g. font-confused 5→9).
    Returns (final_value, votes_counter, confidence_sum, variants_list).
    """
    variants = list(_preprocess(img))
    votes: Counter = Counter()
    confidence_sum: dict[int, float] = {}
    digit_evidence: dict[int, int] = {}
    for _, variant in variants:
        for config in OCR_CONFIGS:
            numbers, avg_conf, digits_in_text = _ocr_call(variant, config)
            for val in numbers:
                votes[val] += 1
                confidence_sum[val] = confidence_sum.get(val, 0.0) + avg_conf
                if digits_in_text > digit_evidence.get(val, 0):
                    digit_evidence[val] = digits_in_text

    if not votes:
        return None, votes, confidence_sum, variants
    ranked = sorted(
        votes.items(),
        key=lambda kv: (kv[1], confidence_sum.get(kv[0], 0.0), digit_evidence.get(kv[0], 0)),
        reverse=True,
    )
    return ranked[0][0], votes, confidence_sum, variants


def _ocr_image(img: Image.Image):
    """Thin wrapper for callers that only need the voted value."""
    value, _, _, _ = _ocr_image_core(img)
    return value


def _grab(sct, region) -> Image.Image:
    x, y, w, h = region
    bbox = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
    raw = sct.grab(bbox)
    return Image.frombytes("RGB", raw.size, raw.rgb)


def capture_all(regions: dict) -> dict:
    """regions: {label: [x,y,w,h]} -> {label: int|None}.

    Screenshots are grabbed sequentially (mss isn't thread-safe), then OCR
    runs in parallel — tesseract spawns subprocesses that release the GIL,
    so threading gives near-linear speedup across sources.
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
    """Like capture_all, but also returns the binarized variants and vote
    tally per source so a debug UI can inspect what tesseract saw and how
    the vote resolved. Slower than capture_all (carries PIL images back to
    caller); only use when a debug window is open.

    regions: {label: [x,y,w,h]} ->
        {label: {"value": int|None,
                 "bin": PIL.Image | None,
                 "bin_inv": PIL.Image | None,
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
            value, votes, conf_sum, variants = _ocr_image_core(img)
        except Exception:
            return label, {"value": None, "bin": None, "bin_inv": None, "votes": Counter(), "conf": {}}
        variant_map = {name: im for name, im in variants}
        avg_conf = {v: conf_sum[v] / votes[v] for v in votes}
        return label, {
            "value": value,
            "bin": variant_map.get("bin"),
            "bin_inv": variant_map.get("bin_inv"),
            "votes": votes,
            "conf": avg_conf,
        }

    result = {}
    with ThreadPoolExecutor(max_workers=min(len(grabs), 5)) as ex:
        for label, payload in ex.map(ocr_one, grabs.items()):
            result[label] = payload
    return result
