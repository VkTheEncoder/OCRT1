import time
import math

def progress_bar(current, total, bar_length=20):
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)
    percent = (current / total) * 100
    return f"[{bar}] {percent:.1f}%"

def readable_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

async def update_progress(message, prefix, current, total, start_time):
    elapsed = time.time() - start_time
    speed = current / elapsed if elapsed > 0 else 0
    remaining = (total - current) / speed if speed > 0 else 0

    bar = progress_bar(current, total)
    msg = (
        f"{prefix}\n\n"
        f"{bar}\n"
        f"✅ {current/1024/1024:.2f} MB / {total/1024/1024:.2f} MB\n"
        f"⚡ Speed: {speed/1024/1024:.2f} MB/s\n"
        f"⏱️ Elapsed: {readable_time(elapsed)} | ⌛ Remaining: {readable_time(remaining)}"
    )
    await message.edit_text(msg)
