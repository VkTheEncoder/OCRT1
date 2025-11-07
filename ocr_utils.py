import re
import os
import ffmpeg
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

def extract_frames(video_path, output_folder="frames", fps=1):
    os.makedirs(output_folder, exist_ok=True)
    (
        ffmpeg
        .input(video_path)
        .output(f"{output_folder}/frame_%04d.png", vf=f"fps={fps},crop=iw:ih/3:0:ih*2/3")
        .run(quiet=True, overwrite_output=True)
    )
    return sorted([os.path.join(output_folder, f) for f in os.listdir(output_folder) if f.endswith(".png")])

def perform_ocr_on_frames(frames):
    ocr_results = []
    for i, frame in enumerate(frames):
        text_data, _ = ocr(frame)
        if not text_data:
            continue
        all_text = " ".join([x[1] for x in text_data])
        english_text = " ".join(re.findall(r'[A-Za-z0-9\s.,!?\'"-]+', all_text)).strip()
        if english_text:
            ocr_results.append((i, english_text))
    return ocr_results
