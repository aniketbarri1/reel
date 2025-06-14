# main.py
import os
import time
import logging
import schedule
import sqlite3
import asyncio
import nest_asyncio
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes, ClientError
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_IDS = [2119921139]  # Replace with your Telegram user ID

# === CONSTANTS ===
BASE_DIR = os.getcwd()
MAX_RETRIES = 3
MAX_THREADS = 5
executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
last_upload_logs = {}

# === DB SETUP ===
db_path = os.path.join(BASE_DIR, "accounts.db")
conn = sqlite3.connect(db_path, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, password TEXT, caption TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS schedules (username TEXT, time TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS video_captions (username TEXT, filename TEXT, caption TEXT)")
conn.commit()

# === CORE FUNCTIONS ===
def get_accounts():
    cursor.execute("SELECT * FROM accounts")
    return cursor.fetchall()

def get_schedule(username):
    cursor.execute("SELECT time FROM schedules WHERE username = ?", (username,))
    return [row[0] for row in cursor.fetchall()]

def add_schedule(username, time_str):
    cursor.execute("INSERT INTO schedules (username, time) VALUES (?, ?)", (username, time_str))
    conn.commit()

def remove_schedule(username, time_str):
    cursor.execute("DELETE FROM schedules WHERE username = ? AND time = ?", (username, time_str))
    conn.commit()

def load_client(username):
    cl = Client()
    cl.set_device({"manufacturer": "OnePlus", "model": "6T", "android_version": 29})
    session_path = f"session_{username}.json"
    if os.path.exists(session_path):
        try:
            cl.load_settings(session_path)
            cl.login(username, None)
        except:
            os.remove(session_path)
    if not cl.user_id:
        cursor.execute("SELECT password FROM accounts WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            raise Exception(f"Account '{username}' not found.")
        cl.login(username, row[0])
        cl.dump_settings(session_path)
    return cl

def upload_video(cl, video_path, caption):
    for attempt in range(MAX_RETRIES):
        try:
            cl.clip_upload(video_path, caption)
            return f"✅ Uploaded: {os.path.basename(video_path)}"
        except PleaseWaitFewMinutes:
            time.sleep(60 * (attempt + 1))
        except ClientError as e:
            return f"⚠ Client error: {e}"
        except Exception as e:
            return f"❌ Failed: {e}"
    return "❌ Upload failed after retries"

def upload_all_videos(username):
    cl = load_client(username)
    folder = os.path.join(BASE_DIR, username)
    os.makedirs(folder, exist_ok=True)
    files = sorted([f for f in os.listdir(folder) if f.endswith(".mp4")])
    results = []
    cursor.execute("SELECT caption FROM accounts WHERE username = ?", (username,))
    default_caption = cursor.fetchone()[0] or ""
    for file in files:
        path = os.path.join(folder, file)
        cursor.execute("SELECT caption FROM video_captions WHERE username = ? AND filename = ?", (username, file))
        row = cursor.fetchone()
        caption = row[0] if row else default_caption
        result = upload_video(cl, path, caption)
        results.append(result)
        time.sleep(10)
    last_upload_logs[username] = "\n".join(results)

def schedule_upload(username):
    times = get_schedule(username)
    for t in times:
        def job(user=username):
            executor.submit(upload_all_videos, user)
        schedule.every().day.at(t).do(job)

# === TELEGRAM BOT ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Unauthorized.")
        return
    users = get_accounts()
    keyboard = [[InlineKeyboardButton(f"👤 {user[0]}", callback_data=f"user_{user[0]}")] for user in users]
    keyboard.append([InlineKeyboardButton("➕ Add Account", callback_data="add_account")])
    await update.message.reply_text("🤖 Choose Account to Manage:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return await query.edit_message_text("🚫 Unauthorized.")
    data = query.data

    if data == "add_account":
        context.user_data["adding_account"] = True
        await query.edit_message_text("✏️ Send username and password like this:\n`username,password`", parse_mode='Markdown')

    elif data.startswith("user_"):
        username = data.split("_", 1)[1]
        context.user_data["active_user"] = username
        keyboard = [
            [InlineKeyboardButton("📅 View Schedule", callback_data=f"schedule_{username}"),
             InlineKeyboardButton("➕ Add Time", callback_data=f"add_{username}")],
            [InlineKeyboardButton("➖ Remove Time", callback_data=f"remove_{username}"),
             InlineKeyboardButton("🚀 Force Upload", callback_data=f"force_{username}")],
            [InlineKeyboardButton("✏️ Change Caption", callback_data=f"caption_{username}"),
             InlineKeyboardButton("🧾 Last Upload", callback_data=f"status_{username}")]
        ]
        await query.edit_message_text(f"🔧 Manage: {username}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("schedule_"):
        username = data.split("_", 1)[1]
        times = get_schedule(username)
        await query.edit_message_text("📅 Schedule:\n" + "\n".join(times) if times else "No schedule set.")

    elif data.startswith("add_"):
        context.user_data["pending_add"] = data.split("_", 1)[1]
        await query.edit_message_text("🕒 Send time to add (HH:MM):")

    elif data.startswith("remove_"):
        context.user_data["pending_remove"] = data.split("_", 1)[1]
        await query.edit_message_text("🕒 Send time to remove (HH:MM):")

    elif data.startswith("force_"):
        username = data.split("_", 1)[1]
        await query.edit_message_text(f"🚀 Upload started for {username}...")
        async def upload_task():
            try:
                upload_all_videos(username)
                await context.bot.send_message(query.from_user.id, f"✅ Upload finished for {username}\n{last_upload_logs.get(username)}")
            except Exception as e:
                await context.bot.send_message(query.from_user.id, f"❌ Upload error: {e}")
        asyncio.create_task(upload_task())

    elif data.startswith("caption_"):
        context.user_data["pending_caption_edit"] = data.split("_", 1)[1]
        await query.edit_message_text("✏️ Send new caption:")

    elif data.startswith("status_"):
        username = data.split("_", 1)[1]
        await query.edit_message_text(f"🧾 Last Upload:\n{last_upload_logs.get(username, 'No uploads yet')}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "pending_add" in context.user_data:
        username = context.user_data.pop("pending_add")
        add_schedule(username, text)
        await update.message.reply_text(f"✅ Time {text} added.")
    elif "pending_remove" in context.user_data:
        username = context.user_data.pop("pending_remove")
        remove_schedule(username, text)
        await update.message.reply_text(f"✅ Time {text} removed.")
    elif "pending_caption_edit" in context.user_data:
        username = context.user_data.pop("pending_caption_edit")
        cursor.execute("UPDATE accounts SET caption = ? WHERE username = ?", (text, username))
        conn.commit()
        await update.message.reply_text(f"✏️ Caption updated for {username}:\n{text}")
    elif context.user_data.get("adding_account"):
        try:
            uname, pwd = text.split(",", 1)
            cursor.execute("INSERT OR IGNORE INTO accounts (username, password, caption) VALUES (?, ?, '')", (uname.lower(), pwd))
            conn.commit()
            os.makedirs(os.path.join(BASE_DIR, uname.lower()), exist_ok=True)
            context.user_data.pop("adding_account")
            await update.message.reply_text(f"✅ Account `{uname}` added.", parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ Error. Send like this: `username,password`", parse_mode='Markdown')

# === SCHEDULER ===
def start_scheduler():
    for acc in get_accounts():
        schedule_upload(acc[0])
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"❌ Scheduler error: {e}")
        time.sleep(1)

# === STARTUP ===
async def main_async():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    await app.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    executor.submit(start_scheduler)
    nest_asyncio.apply()
    asyncio.run(main_async())
