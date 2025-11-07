import os
import asyncio
import time
from pyrogram import Client, filters
from ocr_utils import extract_frames, perform_ocr_on_frames
from srt_builder import build_srt
from progress_utils import update_progress

API_ID = 25341849          # your Telegram API ID
API_HASH = "c22013816f700253000e3c24a64db3b6"
BOT_TOKEN = "7260809129:AAGiRnpJrr7OqMmZbUovi6wxGP5DF-LVKrg"

app = Client("subtitle_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply(
        "🎬 **Welcome to Subtitle Extractor Bot**\n\n"
        "Send me a video with **hard-coded subtitles** (English + Chinese supported).\n"
        "I’ll extract and send you an `.srt` file containing only **English subtitles.**"
    )

@app.on_message(filters.video | filters.document)
async def extract_subs(client, msg):
    video = msg.video or msg.document
    if not video:
        return await msg.reply("⚠️ Please send a valid video file.")

    temp_msg = await msg.reply("📥 Downloading video...")
    start_time = time.time()

    # Track download progress
    async def download_progress(current, total):
        await update_progress(temp_msg, "📥 Downloading video...", current, total, start_time)

    video_path = await app.download_media(video, file_name="video.mp4", progress=download_progress)

    await temp_msg.edit("🧠 Extracting frames from video...")
    frames = extract_frames(video_path, fps=1)
    await temp_msg.edit(f"📸 Extracted {len(frames)} frames, starting OCR...")

    ocr_results = await perform_ocr_on_frames(frames, temp_msg, app)

    if not ocr_results:
        await temp_msg.edit("😔 No English subtitles detected.")
        cleanup(video_path, frames)
        return

    await temp_msg.edit("📝 Building `.srt` file...")
    srt_content = build_srt(ocr_results)
    with open("output.srt", "w", encoding="utf-8") as f:
        f.write(srt_content)

    # Upload progress
    upload_start = time.time()
    async def upload_progress(current, total):
        await update_progress(temp_msg, "📤 Uploading `.srt` file...", current, total, upload_start)

    await app.send_document(
        msg.chat.id, 
        "output.srt", 
        caption="✅ Here are your extracted English subtitles 🎉",
        progress=upload_progress
    )

    await temp_msg.delete()
    cleanup(video_path, frames)

def cleanup(video_path, frames):
    try:
        os.remove(video_path)
        for f in frames:
            os.remove(f)
        os.rmdir("frames")
    except Exception as e:
        print("Cleanup error:", e)

print("✅ Subtitle Extractor Bot Started...")
app.run()
