import os
import asyncio
from pyrogram import Client, filters
from ocr_utils import extract_frames, perform_ocr_on_frames
from srt_builder import build_srt

API_ID = 12345          # your Telegram API ID
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token_here"

app = Client("subtitle_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("🎬 Send me a video and I'll extract **English subtitles** (burned-in) for you in `.srt` format.\n\nPlease wait patiently while I process your video.")

@app.on_message(filters.video | filters.document)
async def extract_subs(_, msg):
    video = msg.video or msg.document
    if not video:
        return await msg.reply("⚠️ Please send a valid video file.")
    
    processing = await msg.reply("⏳ Downloading video...")
    video_path = await app.download_media(video, file_name="video.mp4")

    await processing.edit("🧠 Extracting frames and running OCR... This might take a few minutes.")
    frames = extract_frames(video_path, fps=1)
    ocr_results = perform_ocr_on_frames(frames)

    if not ocr_results:
        await processing.edit("😔 No English subtitles detected.")
        cleanup(video_path, frames)
        return

    await processing.edit("📝 Building .srt file...")
    srt_content = build_srt(ocr_results)
    with open("output.srt", "w", encoding="utf-8") as f:
        f.write(srt_content)

    await app.send_document(msg.chat.id, "output.srt", caption="Here are your extracted English subtitles 🎉")

    await processing.delete()
    cleanup(video_path, frames)

def cleanup(video_path, frames):
    try:
        os.remove(video_path)
        for f in frames:
            os.remove(f)
        os.rmdir("frames")
    except:
        pass

print("✅ Bot started!")
app.run()
