"""Screenshot 4 regions and OCR them into integer peak viewer counts."""
import os
import re
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import mss
import pytesseract
from PIL import Image, ImageFilter, ImageOps

# Auto-detect Tesseract path on Windows if not in PATH
if not shutil.which("tesseract"):
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


def _ocr_image_core(img: Image.Image):
    """Run OCR with multiple preprocessings + PSM modes, vote across readings.
    Returns (final_value, votes_counter, variants_list).
    Variants are kept so debug callers can show what tesseract actually saw.
    """
    variants = list(_preprocess(img))
    votes: Counter = Counter()
    digit_evidence: dict[int, int] = {}
    for _, variant in variants:
        for config in OCR_CONFIGS:
            try:
                text = pytesseract.image_to_string(variant, config=config)
            except Exception:
                continue
            digits_in_text = sum(1 for c in text if c.isdigit())
            for val in _extract_numbers(text):
                votes[val] += 1
                if digits_in_text > digit_evidence.get(val, 0):
                    digit_evidence[val] = digits_in_text

    if not votes:
        return None, votes, variants
    ranked = sorted(
        votes.items(),
        key=lambda kv: (kv[1], digit_evidence.get(kv[0], 0), kv[0]),
        reverse=True,
    )
    return ranked[0][0], votes, variants


def _ocr_image(img: Image.Image):
    """Thin wrapper for callers that only need the voted value."""
    value, _, _ = _ocr_image_core(img)
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
