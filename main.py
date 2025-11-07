import os
import asyncio
import time
import logging
import traceback
import tempfile  
import shutil    
from datetime import datetime
from pyrogram import Client, filters
from ocr_utils import extract_frames, perform_ocr_on_frames
from srt_builder import build_srt
from progress_utils import update_progress

# ========== CONFIG ==========
API_ID = 25341849          # your Telegram API ID
API_HASH = "c22013816f700253000e3c24a64db3b6"
BOT_TOKEN = "7260809129:AAGmpo4xGrXVk_7emrW9hCQK3vL9dXhzq3A"
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

# ========== LOGGING SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Client("subtitle_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ========== START COMMAND ==========
@app.on_message(filters.command("start"))
async def start(_, msg):
    logger.info(f"User {msg.from_user.id} started bot.")
    await msg.reply(
        "🎬 **Welcome to Subtitle Extractor Bot**\n\n"
        "Send me a video with hard-coded subtitles (English + Chinese supported).\n"
        "I’ll extract and send you an `.srt` file containing only **English subtitles.**"
    )

# ========== MAIN HANDLER ==========
@app.on_message(filters.video | filters.document)
async def extract_subs(client, msg):
    
    # Create a unique directory for this one job
    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = None  # Define here for the 'except' block
        
        try:
            video = msg.video or msg.document
            if not video:
                await msg.reply("⚠️ Please send a valid video file.")
                return

            logger.info(f"Processing started for user {msg.from_user.id} | File: {video.file_name} | TempDir: {temp_dir}")
            temp_msg = await msg.reply("📥 Downloading video...")
            start_time = time.time()

            # --- DOWNLOAD ---
            async def download_progress(current, total):
                await update_progress(temp_msg, "📥 Downloading video...", current, total, start_time)

            # Use the temp_dir for the video path
            video_path = await app.download_media(
                video,
                file_name=os.path.join(temp_dir, "video.mp4"),
                progress=download_progress
            )
            file_size = os.path.getsize(video_path)
            logger.info(f"Download complete | File size: {file_size / (1024*1024):.2f} MB")

            # --- Define a single FPS for processing ---
            PROCESSING_FPS = 3 # Or 1, 2, etc.
            
            # --- FRAME EXTRACTION ---
            await temp_msg.edit(f"🧠 Extracting frames at {PROCESSING_FPS} FPS...")
            # Use the temp_dir for the frames path
            frames_dir = os.path.join(temp_dir, "frames")
            frames = extract_frames(video_path, output_folder=frames_dir, fps=PROCESSING_FPS)
            logger.info(f"Extracted {len(frames)} frames.")

            # --- OCR PROCESS ---
            await temp_msg.edit(f"📸 {len(frames)} frames ready, starting OCR...")
            ocr_results = await perform_ocr_on_frames(frames, temp_msg, app, fps=PROCESSING_FPS)
            logger.info(f"OCR completed | Detected {len(ocr_results)} English lines.")

            if not ocr_results:
                await temp_msg.edit("😔 No English subtitles detected.")
                logger.warning("No subtitles found in video.")
                # No cleanup needed, 'with' statement handles it
                return

            # --- SRT BUILD ---
            await temp_msg.edit("📝 Building `.srt` file...")
            
            # Run the slow, synchronous function in a separate thread
            srt_content = await asyncio.to_thread(
                build_srt,
                ocr_results,
                fps=PROCESSING_FPS
            )
            
            # Use the temp_dir for the srt path
            srt_path = os.path.join(temp_dir, "output.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            logger.info("SRT file created successfully.")

            # --- UPLOAD ---
            upload_start = time.time()
            async def upload_progress(current, total):
                await update_progress(temp_msg, "📤 Uploading `.srt` file...", current, total, upload_start)

            await app.send_document(
                msg.chat.id,
                srt_path,  # Send the unique srt file
                caption="✅ Here are your extracted English subtitles 🎉",
                progress=upload_progress
            )

            await temp_msg.delete()
            logger.info(f"Process completed successfully for user {msg.from_user.id}.")

        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"❌ Error for user {msg.from_user.id}: {str(e)}\n{error_trace}")
            await msg.reply("⚠️ An unexpected error occurred. Please check logs for details.")
            # No cleanup needed, 'with' statement handles it
        
        # The 'temp_dir' and all its contents (video, frames, srt)
        # are automatically and safely deleted here

# ========== CLEANUP ==========
def cleanup(video_path, frames):
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.isdir("frames"):
            for f in frames:
                if os.path.exists(f):
                    os.remove(f)
            # safer folder removal with retry
            import shutil, time
            for _ in range(3):
                try:
                    shutil.rmtree("frames")
                    break
                except Exception:
                    time.sleep(0.5)

        if os.path.exists("output.srt"):
            os.remove("output.srt")
        logger.info("🧹 Cleanup complete.")
    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")

# ========== BOT START ==========
logger.info("✅ Subtitle Extractor Bot Started.")
app.run()
