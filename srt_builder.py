import srt
from datetime import timedelta

def build_srt(ocr_results, fps=1):
    subs = []
    for idx, (frame_idx, text) in enumerate(ocr_results):
        start = timedelta(seconds=frame_idx / fps)
        end = timedelta(seconds=(frame_idx + 1.5) / fps)
        subs.append(srt.Subtitle(index=idx + 1, start=start, end=end, content=text))

    merged = merge_duplicates(subs)
    return srt.compose(merged)

def merge_duplicates(subs):
    """Merge consecutive identical subtitles by extending time range."""
    if not subs:
        return subs

    merged = [subs[0]]
    for i in range(1, len(subs)):
        prev = merged[-1]
        current = subs[i]

        # If the text is identical and timestamps overlap or are continuous
        if current.content.strip() == prev.content.strip():
            # Extend the previous end time to current end time
            prev.end = current.end
        else:
            merged.append(current)

    # Reindex subtitles
    for i, sub in enumerate(merged, start=1):
        sub.index = i

    return merged
