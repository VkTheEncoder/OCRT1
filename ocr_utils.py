import re
import os
import ffmpeg
import time
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

def extract_frames(video_path, output_folder="frames", fps=3):
    os.makedirs(output_folder, exist_ok=True)
    (
        ffmpeg
        .input(video_path)
        .output(f"{output_folder}/frame_%04d.png", vf=f"fps={fps},crop=iw:ih/3:0:ih*2/3")
        .run(quiet=True, overwrite_output=True)
    )
    return sorted([os.path.join(output_folder, f) for f in os.listdir(output_folder) if f.endswith(".png")])

async def perform_ocr_on_frames(frames, progress_msg, app, fps=3):
    ocr_results = []
    total = len(frames)
    start_time = time.time()

    for i, frame in enumerate(frames, start=1):
        text_data, _ = ocr(frame)
        if text_data:
            all_text = " ".join([x[1] for x in text_data])
            english_text = " ".join(re.findall(r'[A-Za-z0-9\s.,!?\'"-]+', all_text)).strip()
            if english_text:
                ocr_results.append((i, english_text))

        # Update OCR progress every 10 frames
        if i % 10 == 0 or i == total:
            elapsed = time.time() - start_time
            percent = (i / total) * 100
            remaining = (elapsed / i) * (total - i) if i > 0 else 0
            bar = int(percent // 5) * "█" + int((100 - percent) // 5) * "░"
            await progress_msg.edit_text(
                f"🧠 Running OCR on frames...\n\n"
                f"[{bar}] {percent:.1f}%\n"
                f"Processed: {i}/{total} frames\n"
                f"⏱️ Elapsed: {elapsed:.1f}s | ⌛ Remaining: {remaining:.1f}s"
            )

    return ocr_results
