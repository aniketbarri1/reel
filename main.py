import os
import time
import logging
import schedule
import json
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes, ClientError
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import asyncio

# === SETTINGS ===
BASE_DIR = os.getcwd()
  # Update if folder is elsewhere
MAX_RETRIES = 3
MAX_THREADS = 3
executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

# === TELEGRAM CONFIG ===
TELEGRAM_TOKEN = "7656010953:AAGTRV5AYi2Ci641hP9nPg-zkXfjPsOnHms"
ADMIN_USER_ID = 2119921139
last_upload_log = "No uploads yet."

# === ACCOUNTS ===
accounts = [
    {
        "username": "bgmi_hack07",
        "password": "567567",
        "upload_times": ["13:24", "16:30", "19:30", "22:30", "01:30", "04:30", "07:30", "10:30", "12:00", "12:47"],
        "upload_delay": 30,
        "caption": "💥 #Hack download link 🖇️ bio #bgmi #pubg #trending #battlegroundmobileindia #bgmifunny #funny #pubgmoments #bgmilovers❤️ #feed #explore #pubgmoments #pubgm #pubgmobile #pubgvideos #pubgmeme #pubgfunny #fyp #pub"
    }
]

# === FUNCTIONS ===
def load_client(username):
    cl = Client()
    cl.set_device({"manufacturer": "OnePlus", "model": "6T", "android_version": 29})
    session_path = f"session_{username}.json"
    try:
        if os.path.exists(session_path):
            cl.load_settings(session_path)
            cl.login(username, None)
            logging.info(f"✅ Session loaded for {username}")
        else:
            raise FileNotFoundError
    except (LoginRequired, FileNotFoundError):
        logging.warning(f"🔐 Login required for {username}")
        password = next(acc['password'] for acc in accounts if acc['username'] == username)
        cl.login(username, password)
        cl.dump_settings(session_path)
        logging.info(f"💾 New session saved for {username}")
    return cl

def upload_video(cl, video_path, caption):
    global last_upload_log
    for attempt in range(MAX_RETRIES):
        try:
            logging.info(f"⬆️ Uploading {video_path}")
            cl.clip_upload(video_path, caption)
            last_upload_log = f"✅ Uploaded: {video_path}"
            return True
        except PleaseWaitFewMinutes:
            wait_time = 60 * (attempt + 1)
            logging.warning(f"⏳ Rate limit. Waiting {wait_time}s...")
            last_upload_log = f"⏳ Rate limit. Waiting {wait_time}s..."
            time.sleep(wait_time)
        except ClientError as e:
            logging.error(f"⚠️ Client error: {e}")
            last_upload_log = f"⚠️ Client error: {e}"
            return False
        except Exception as e:
            logging.error(f"❌ Failed to upload {video_path}: {e}")
            last_upload_log = f"❌ Failed: {e}"
    return False

def upload_all_videos(username):
    account = next(acc for acc in accounts if acc["username"] == username)
    upload_delay = account.get("upload_delay", 10)
    caption = account.get("caption", "")
    cl = load_client(username)

    folder = os.path.join(BASE_DIR, username)
    if not os.path.isdir(folder):
        logging.warning(f"📁 Folder not found for {username}")
        return

    files = sorted([f for f in os.listdir(folder) if f.endswith(".mp4")])
    for file in files:
        path = os.path.join(folder, file)
        success = upload_video(cl, path, caption)
        if not success:
            logging.error(f"⚠️ Skipped: {file}")
        time.sleep(upload_delay)

def schedule_upload(account):
    for t in account["upload_times"]:
        schedule.every().day.at(t).do(lambda acc=account["username"]: executor.submit(upload_all_videos, acc))
        logging.info(f"📅 Scheduled {account['username']} at {t}")

# === TELEGRAM HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return await update.message.reply_text("🚫 Unauthorized.")

    keyboard = [
        [InlineKeyboardButton("📅 View Schedule", callback_data='view_schedule')],
        [InlineKeyboardButton("📂 Videos Left", callback_data='videos_left')],
        [InlineKeyboardButton("🚀 Force Upload Now", callback_data='force_upload')],
        [InlineKeyboardButton("🧾 Last Upload Status", callback_data='last_status')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🤖 Bot Control Panel", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_upload_log
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_USER_ID:
        return await query.edit_message_text("🚫 Unauthorized.")

    if query.data == "view_schedule":
        times = "\n".join(accounts[0]["upload_times"])
        await query.edit_message_text(f"📅 Schedule:\n{times}")

    elif query.data == "videos_left":
        folder = os.path.join(BASE_DIR, accounts[0]["username"])
        count = len([f for f in os.listdir(folder) if f.endswith(".mp4")])
        await query.edit_message_text(f"📂 {count} videos left to upload.")

    elif query.data == "force_upload":
        username = accounts[0]["username"]
        executor.submit(upload_all_videos, username)
        await query.edit_message_text("🚀 Upload started manually.")

    elif query.data == "last_status":
        await query.edit_message_text(f"🧾 Last Upload:\n{last_upload_log}")

# === MAIN ENTRY ===
def start_scheduler():
    for account in accounts:
        schedule_upload(account)
    logging.info("✅ Scheduler ready. Waiting...")
    while True:
        schedule.run_pending()
        time.sleep(1)

async def main_async():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    await app.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    executor.submit(start_scheduler)
    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    executor.submit(start_scheduler)

    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_async())

