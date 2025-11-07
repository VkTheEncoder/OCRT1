import srt
from datetime import timedelta

def build_srt(ocr_results, fps=1):
    subs = []
    for idx, (frame_idx, text) in enumerate(ocr_results):
        start = timedelta(seconds=frame_idx / fps)
        end = timedelta(seconds=(frame_idx + 1.5) / fps)
        subs.append(srt.Subtitle(index=idx+1, start=start, end=end, content=text))
    return srt.compose(subs)
