# srt_builder.py
import srt
from datetime import timedelta
from difflib import SequenceMatcher
import re

# ---------- Tuning knobs ----------
MIN_SHOW = 0.90        # minimum on-screen duration (sec)
MAX_MERGE_GAP = 0.40   # if same/similar text reappears within this gap, extend previous line (sec)
CHANGE_CONFIRM = 2     # require N consecutive frames of *different* text to confirm a change
SIM_THRESHOLD = 0.92   # similarity to treat two strings as equivalent
# ----------------------------------

_punct_map = str.maketrans({
    "’":"'", "‘":"'", "“":'"', "”":'"', "—":"-", "–":"-"
})

_space_re = re.compile(r"\s+")
_punct_re = re.compile(r"\s*([,.;:?!])\s*")
_quotes_fix = re.compile(r"\s*'\s*|\s*\"\s*")

def _normalize(txt: str) -> str:
    """
    Normalize OCR text so tiny visual differences don't split lines.
    - unify quotes/dashes
    - collapse spaces
    - normalize punctuation spacing
    - lowercasing (optional; keeps case-insensitive)
    """
    t = (txt or "").strip().translate(_punct_map)
    t = _punct_re.sub(lambda m: m.group(1), t)       # no spaces around punctuation
    t = _quotes_fix.sub(lambda m: m.group(0).strip().replace(" ", ""), t)
    t = _space_re.sub(" ", t)                        # collapse spaces
    t = t.strip()
    return t

def _similar(a: str, b: str, th=SIM_THRESHOLD) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    # light canonicalization so "." vs "," doesn't split
    a = _normalize(a.replace(",", "."))
    b = _normalize(b.replace(",", "."))
    return SequenceMatcher(None, a, b).ratio() >= th

def build_srt(ocr_results, fps, total_frames=None):
    """
    ocr_results: list of (frame_idx:int, text:str) sorted by frame_idx
    fps: frames per second used during extraction
    total_frames: optional; if known, last line will be clamped to this
    """
    if not ocr_results:
        return ""

    # Debounced run detection with hysteresis:
    segments = []  # (start_frame, end_frame, canonical_text, raw_text_to_show)
    curr_text = _normalize(ocr_results[0][1])
    raw_keep = ocr_results[0][1].strip()
    start_f = ocr_results[0][0]

    # counters to confirm changes (avoid flicker)
    diff_streak = 0
    last_seen_same = ocr_results[0][0]

    def _close_segment(s, e, text, raw):
        # ensure minimum duration, and no negative
        if e < s:
            e = s
        # enforce min duration
        if (e - s + 1) / fps < MIN_SHOW:
            e = s + max(int(MIN_SHOW * fps) - 1, 0)
        segments.append((s, e, text, raw))

    for i in range(1, len(ocr_results)):
        idx, raw = ocr_results[i]
        norm = _normalize(raw)

        if _similar(norm, curr_text):
            # same (or near-same) text continues
            diff_streak = 0
            last_seen_same = idx
            # keep the "best-looking" raw version (longer content is usually cleaner)
            if len(raw.strip()) > len(raw_keep):
                raw_keep = raw.strip()
            continue

        # different text detected; confirm change
        diff_streak += 1
        if diff_streak >= CHANGE_CONFIRM:
            # finalize previous run up to last frame where it was same
            _close_segment(start_f, last_seen_same, curr_text, raw_keep)
            # start new run
            curr_text = norm
            raw_keep = raw.strip()
            start_f = idx
            diff_streak = 0
            last_seen_same = idx

    # finalize last open run
    end_last = last_seen_same
    if total_frames is not None:
        end_last = min(end_last, total_frames - 1)
    _close_segment(start_f, end_last, curr_text, raw_keep)

    # Merge segments separated by very small gaps if they are still similar
    merged = []
    for s, e, txt, raw in segments:
        if not merged:
            merged.append([s, e, txt, raw])
            continue
        ps, pe, ptxt, praw = merged[-1]
        # gap between previous end and current start
        gap = (s - pe - 1) / fps
        if gap <= MAX_MERGE_GAP and _similar(txt, ptxt):
            # extend previous; prefer cleaner raw
            merged[-1][1] = e
            if len(raw) > len(praw):
                merged[-1][3] = raw
        else:
            merged.append([s, e, txt, raw])

    # Compose SRT with guaranteed non-overlap and tiny safety gap
    subs = []
    last_end_sec = -1.0
    for i, (s, e, _txt, raw) in enumerate(merged, 1):
        start_sec = max(s / fps, last_end_sec)       # never before previous end
        end_sec = (e + 1) / fps

        # enforce ordering + min duration
        if end_sec - start_sec < MIN_SHOW:
            end_sec = start_sec + MIN_SHOW

        # no overlaps
        if start_sec < last_end_sec:
            start_sec = last_end_sec
        if end_sec < start_sec:
            end_sec = start_sec + MIN_SHOW

        subs.append(
            srt.Subtitle(
                index=i,
                start=timedelta(seconds=start_sec),
                end=timedelta(seconds=end_sec),
                content=raw.strip()
            )
        )
        last_end_sec = end_sec

    return srt.compose(subs)
