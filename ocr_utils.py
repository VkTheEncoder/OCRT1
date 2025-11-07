# ocr_utils.py — hard-sub OCR utilities (no SRT overlap logic here)

import os
import re
import time
import ffmpeg
import cv2
import numpy as np
from typing import List, Tuple, Optional
from rapidocr_onnxruntime import RapidOCR

# ----------------- OCR engine -----------------
ocr = RapidOCR()

# ----------------- Tuning knobs -----------------
DEFAULT_FPS = 3

# Skip OCR if subtitle strip looks visually unchanged vs previous frame
CHANGE_THRESHOLD = 6.0     # raise to skip more frames, lower to OCR more often

# Treat lines as the same if only tiny changes (comma/period/space)
SIM_THRESHOLD = 0.92
# ------------------------------------------------

# ---------- Helpers ----------
_num_re = re.compile(r"\d+")
_english_keep = re.compile(r"[A-Za-z0-9\s\.\,\!\?\'\"\-\:;]+")

def _parse_frame_index(path: str) -> int:
    """Extract integer index from filenames like frame_0001.png."""
    digits = _num_re.findall(os.path.basename(path))
    return int(digits[-1]) if digits else 0

def _prep_img(img_bgr: np.ndarray) -> np.ndarray:
    """
    Light preprocessing to stabilize OCR:
      - grayscale
      - bilateral denoise (keeps edges)
      - adaptive threshold to binary
    """
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.bilateralFilter(g, 7, 75, 75)
    g = cv2.adaptiveThreshold(
        g, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 9
    )
    return g

def _similar(a: str, b: str, th: float = SIM_THRESHOLD) -> bool:
    """Quick similarity for debounce (handles ., , , quotes, extra spaces)."""
    def canon(t: str) -> str:
        t = (t or "").strip()
        t = t.replace(",", ".")
        t = re.sub(r"\s+", " ", t)
        t = t.translate(str.maketrans({"’":"'", "‘":"'", "“":'"', "”":'"', "—":"-", "–":"-"}))
        return t
    a, b = canon(a), canon(b)
    if not a and not b:
        return True
    if not a or not b:
        return False
    sa, sb = set(a.split()), set(b.split())
    if not sa and not sb:
        return True
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    jacc = inter / union
    if jacc >= th:
        return True
    if min(len(a), len(b)) < 12:
        same = sum(1 for x, y in zip(a, b) if x == y)
        return same / max(len(a), len(b)) >= th
    return False
# -----------------------------------------------


def extract_frames(
    video_path: str,
    output_folder: str = "frames",
    fps: int = DEFAULT_FPS,
    crop_bottom_third: bool = True,
    crop_custom: Optional[str] = None,
) -> List[str]:
    """
    Extract frames from the subtitle band using ffmpeg.
    - If crop_custom is provided, it's appended after fps (e.g. "crop=iw:ih/3:0:ih*2/3").
    - If crop_bottom_third=True, uses bottom third crop by default.
    Returns a list of frame paths sorted by numeric index.
    """
    os.makedirs(output_folder, exist_ok=True)

    vf_parts = [f"fps={fps}"]
    if crop_custom:
        vf_parts.append(crop_custom)
    elif crop_bottom_third:
        vf_parts.append("crop=iw:ih/3:0:ih*2/3")
    vf = ",".join(vf_parts)

    (
        ffmpeg
        .input(video_path)
        .output(f"{output_folder}/frame_%04d.png", vf=vf)
        .run(quiet=True, overwrite_output=True)
    )

    frames = [os.path.join(output_folder, f) for f in os.listdir(output_folder) if f.endswith(".png")]
    frames.sort(key=_parse_frame_index)
    return frames


async def perform_ocr_on_frames(
    frames: List[str],
    progress_msg,
    app,                 # kept for compatibility with your caller
    fps: int = DEFAULT_FPS,
) -> List[Tuple[int, str]]:
    results: List[Tuple[int, str]] = []
    total = len(frames)
    start_time = time.time()

    prev_bin = None
    last_text = ""  # last non-empty text

    for i, fp in enumerate(frames, start=1):
        fidx = _parse_frame_index(fp)
        img = cv2.imread(fp)
        if img is None:
            results.append((fidx, ""))
            continue

        binimg = _prep_img(img)

        # Visual-change gating
        if prev_bin is not None:
            diff = cv2.absdiff(binimg, prev_bin)
            score = float(diff.mean())
            if score < CHANGE_THRESHOLD:
                results.append((fidx, ""))  # unchanged visually
            else:
                # OCR only when changed
                o = ocr(binimg)

                clean_parts = []
                if isinstance(o, tuple) and len(o) >= 2:
                    text_score_list = o[1] or []  # This is [('text', score), ...]
                    # Iterate through the list and extract the text (t[0])
                    for t_s_pair in text_score_list:
                        if isinstance(t_s_pair, (list, tuple)) and len(t_s_pair) >= 1:
                            if isinstance(t_s_pair[0], str):
                                val = t_s_pair[0].strip()
                                if val:
                                    clean_parts.append(val)
                
                # This handles the default RapidOCR() return format.
                # The old 'elif isinstance(o, list)' is likely dead code
                # for a different version or a different part of the library.
                
                raw = " ".join(clean_parts)

                eng = " ".join(_english_keep.findall(raw)).strip()

                if eng and _similar(eng, last_text):
                    eng = ""  # near-identical → keep previous alive
                if eng:
                    last_text = eng

                results.append((fidx, eng))
                prev_bin = binimg
        else:
            # First frame
            o = ocr(binimg)
            
            clean_parts = []
            if isinstance(o, tuple) and len(o) >= 2:
                text_score_list = o[1] or []  # This is [('text', score), ...]
                for text, score in text_score_list:
                    if isinstance(text, str):
                        val = text.strip()
                        if val:
                            clean_parts.append(val)
            
            raw = " ".join(clean_parts)
            eng = " ".join(_english_keep.findall(raw)).strip()
            if eng:
                last_text = eng
            results.append((fidx, eng))
            prev_bin = binimg

        # Progress UI
        if i % 10 == 0 or i == total:
            elapsed = time.time() - start_time
            percent = (i / total) * 100
            remaining = (elapsed / i) * (total - i) if i > 0 else 0
            bar = int(percent // 5) * "█" + int((100 - percent) // 5) * "░"
            await progress_msg.edit_text(
                f"🧠 Running OCR on frames…\n\n"
                f"[{bar}] {percent:.1f}%\n"
                f"Processed: {i}/{total} frames\n"
                f"⏱️ Elapsed: {elapsed:.1f}s | ⌛ Remaining: {remaining:.1f}s"
            )

    results.sort(key=lambda x: x[0])
    return results
