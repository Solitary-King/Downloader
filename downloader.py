import os
import sqlite3
import logging
import asyncio
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest
import yt_dlp

# ==================== RENDER PORT CHECK SERVER ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Running Live!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# Downloads ডিরেক্টরি নিশ্চিতকরণ
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8914943378:AAH5uJ-IZYZa6ighXT1OUxglfGFKkPnwKm4"  # আপনার টেলিগ্রাম বট টোকেন
ADMIN_ID = 6535070545  # আপনার টেলিগ্রাম Numeric ID
DB_NAME = "bot_data.db"

logging.basicConfig(level=logging.INFO)

MENU_BUTTONS = ["📥 Download Video", "👤 Profile", "👑 Admin Panel"]

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            total_downloads INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== DATABASE HELPERS ====================
def get_user_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT total_downloads FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0

def add_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        uname = username if username else "NoUsername"
        cursor.execute(
            "INSERT INTO users (user_id, username, total_downloads) VALUES (?, ?, 0)",
            (user_id, uname)
        )
        conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_url FROM channels")
    channels = cursor.fetchall()
    conn.close()
    return channels

def add_channel_db(channel_id, channel_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_url) VALUES (?, ?)", (channel_id, channel_url))
    conn.commit()
    conn.close()

def remove_channel_db(channel_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def increment_download(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, total_downloads) VALUES (?, 'NoUsername', 0)", (user_id,))
    cursor.execute("UPDATE users SET total_downloads = COALESCE(total_downloads, 0) + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_downloads) FROM users")
    res = cursor.fetchone()[0]
    total_dl = res if res is not None else 0
    conn.close()
    return total_users, total_dl

# ==================== FORCE JOIN CHECK ====================
async def check_force_join(user_id, context: ContextTypes.DEFAULT_TYPE):
    channels = get_channels()
    not_joined = []
    
    for ch_id, ch_url in channels:
        try:
            try:
                chat_target = int(ch_id)
            except ValueError:
                chat_target = ch_id

            member = await context.bot.get_chat_member(chat_id=chat_target, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append((ch_id, ch_url))
        except Exception as e:
            logging.error(f"Force Join Error for Channel {ch_id}: {e}")
            not_joined.append((ch_id, ch_url))
            
    return not_joined

# ==================== KEYBOARDS ====================
def main_reply_keyboard(user_id):
    keyboard = [
        [KeyboardButton("📥 Download Video"), KeyboardButton("👤 Profile")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def platform_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 TikTok", callback_data="plat_tiktok"), InlineKeyboardButton("▶️ YouTube", callback_data="plat_youtube")],
        [InlineKeyboardButton("📸 Instagram", callback_data="plat_instagram"), InlineKeyboardButton("📘 Facebook", callback_data="plat_facebook")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== START HANDLER ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user

    add_user(user.id, user.username or user.first_name)

    not_joined = await check_force_join(user.id, context)
    if not_joined:
        keyboard = []
        for idx, (ch_id, ch_url) in enumerate(not_joined, 1):
            keyboard.append([InlineKeyboardButton(f"📢 চ্যানেল {idx}-এ জয়েন করুন", url=ch_url)])
        keyboard.append([InlineKeyboardButton("✅ Check Join", callback_data="check_join")])
        
        await update.message.reply_text(
            "⚠️ **বটটি ব্যবহার করতে আপনাকে অবশ্যই আমাদের সকল চ্যানেলে জয়েন করতে হবে!**\n\nনিচের লিংকগুলোতে জয়েন করে 'Check Join' বাটনে চাপ দিন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"👋 **স্বাগতম {user.first_name}!**\n\nনিচের বাটন চাপুন অথবা সরাসরি যেকোনো ভিডিও লিংক পাঠিয়ে ফ্রি-তে ডাউনলোড করুন:",
        reply_markup=main_reply_keyboard(user.id),
        parse_mode="Markdown"
    )

# ==================== INLINE CALLBACK ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data == "check_join":
        not_joined = await check_force_join(user_id, context)
        if not_joined:
            await query.answer("❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি! সব চ্যানেলে জয়েন করে আবার চেষ্টা করুন।", show_alert=True)
            return
        else:
            await query.answer("✅ ভেরিফিকেশন সফল হয়েছে!", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
                
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ **অভিনন্দন! আপনার ভেরিফিকেশন সফল হয়েছে।**\n\nএখন যেকোনো সোশ্যাল মিডিয়ার লিংক পাঠান:",
                reply_markup=main_reply_keyboard(user_id),
                parse_mode="Markdown"
            )
            return

    elif data.startswith("plat_"):
        platform = data.split("_")[1].capitalize()
        await query.message.reply_text(
            f"📱 **নির্বাচিত প্ল্যাটফর্ম:** {platform}\n\n🔗 অনুগ্রহ করে আপনার **{platform}** ভিডিও লিংকটি এখানে পাঠান।",
            parse_mode="Markdown"
        )

    elif data.startswith("dlvideo_"):
        await query.message.delete()
        await process_media_download(update, context, format_type="video")

    elif data.startswith("dlaudio_"):
        await query.message.delete()
        await process_media_download(update, context, format_type="audio")

    elif user_id == ADMIN_ID:
        if data == "adm_stats":
            tot_users, tot_dl = get_stats()
            await query.message.reply_text(f"📊 **বট পরিসংখ্যান (এডমিন ভিউ)**\n\n👥 মোট ইউজার: {tot_users}\n📥 মোট ডাউনলোড: {tot_dl}", parse_mode="Markdown")
        
        elif data == "adm_listch":
            channels = get_channels()
            if not channels:
                await query.message.reply_text("ℹ️ কোনো চ্যানেল যুক্ত করা নেই।")
                return
            msg = "📢 **ফোর্স জয়েন চ্যানেল তালিকা:**\n\n"
            for ch_id, ch_url in channels:
                msg += f"• `{ch_id}` ➡️ [Link]({ch_url})\n"
            await query.message.reply_text(msg, parse_mode="Markdown")

        elif data == "adm_addch":
            context.user_data['state'] = 'ADD_CHANNEL'
            await query.message.reply_text(
                "✍️ চ্যানেলের **ID/Username** এবং **লিংক** একই সাথে স্পেস (Space) দিয়ে পাঠান।\n\n"
                "**যেমন:**\n`@solitary_hacker https://t.me/solitary_hacker`",
                parse_mode="Markdown"
            )

        elif data == "adm_remch":
            context.user_data['state'] = 'REM_CHANNEL'
            await query.message.reply_text("✍️ রিমুভ করতে চাওয়া চ্যানেলের ID বা Username দিন (যেমন: `@solitary_hacker`):")

        elif data == "adm_bcast":
            context.user_data['state'] = 'BROADCAST'
            await query.message.reply_text("📢 সকল ইউজারের কাছে যে মেসেজ পাঠাতে চান তা লিখুন:")

# ==================== TEXT MESSAGES & STATE HANDLER ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = context.user_data.get('state', None)

    if text in MENU_BUTTONS:
        context.user_data.clear()
        
        if text == "📥 Download Video":
            await update.message.reply_text(
                "👇 **নিচে থেকে প্ল্যাটফর্ম নির্বাচন করুন অথবা সরাসরি যেকোনো ভিডিও লিংক পাঠান:**",
                reply_markup=platform_inline_keyboard(),
                parse_mode="Markdown"
            )
            return

        elif text == "👤 Profile":
            add_user(user_id, update.effective_user.username or update.effective_user.first_name)
            total_dl = get_user_downloads(user_id)
            username_val = update.effective_user.username or update.effective_user.first_name
            username_display = f"@{username_val}" if update.effective_user.username else username_val

            profile_msg = (
                f"👤 **আপনার প্রোফাইল**\n\n"
                f"🆔 **ইউজার আইডি:** `{user_id}`\n"
                f"👤 **ইউজারনেম:** {username_display}\n"
                f"⚡ **স্ট্যাটাস:** 🟢 আনলিমিটেড ফ্রি ইউজার\n"
                f"📥 **মোট ডাউনলোড:** {total_dl}"
            )
            await update.message.reply_text(profile_msg, parse_mode="Markdown")
            return

        elif text == "👑 Admin Panel" and user_id == ADMIN_ID:
            admin_kbd = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Broadcast", callback_data="adm_bcast"), InlineKeyboardButton("📊 User Stats", callback_data="adm_stats")],
                [InlineKeyboardButton("➕ Add Channel", callback_data="adm_addch"), InlineKeyboardButton("🗑️ Remove Channel", callback_data="adm_remch")],
                [InlineKeyboardButton("📜 List Channels", callback_data="adm_listch")]
            ])
            await update.message.reply_text("👑 **এডমিন কন্ট্রোল প্যানেল**\n\nনিচের অপশনগুলো দিয়ে বট পরিচালনা করুন:", reply_markup=admin_kbd, parse_mode="Markdown")
            return

    # Admin Inputs
    if user_id == ADMIN_ID and state:
        if state == 'ADD_CHANNEL':
            parts = text.split()
            if len(parts) >= 2 and parts[1].startswith("http"):
                add_channel_db(parts[0], parts[1])
                await update.message.reply_text(f"✅ **চ্যানেল সফলভাবে যুক্ত করা হয়েছে!**\n\n🔹 ID: `{parts[0]}`\n🔗 Link: {parts[1]}", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ **ভুল ফরমেট!** স্পেস দিয়ে চ্যানেল আইডি এবং সঠিক লিংক দিন।")
            context.user_data.clear()
            return

        elif state == 'REM_CHANNEL':
            remove_channel_db(text)
            await update.message.reply_text(f"🗑️ চ্যানেল `{text}` সফলভাবে রিমুভ করা হয়েছে!", parse_mode="Markdown")
            context.user_data.clear()
            return

        elif state == 'BROADCAST':
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()

            sent, failed = 0, 0
            msg = await update.message.reply_text("📢 **ব্রডকাস্ট চালু রয়েছে...**")

            for u in users:
                try:
                    await context.bot.send_message(chat_id=u[0], text=f"📢 **বিজ্ঞপ্তি:**\n\n{text}", parse_mode="Markdown")
                    sent += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1

            await msg.edit_text(f"✅ **ব্রডকাস্ট সম্পন্ন!**\n\nসফল: {sent}\nব্যর্থ: {failed}", parse_mode="Markdown")
            context.user_data.clear()
            return

    # Force Join Check
    not_joined = await check_force_join(user_id, context)
    if not_joined:
        await update.message.reply_text("⚠️ আপনাকে অবশ্যই প্রথমে চ্যানেলে জয়েন করতে হবে! /start দিন।")
        return

    # Link Receiver
    if text.startswith("http://") or text.startswith("https://"):
        context.user_data['pending_url'] = text
        
        format_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎥 Video (MP4)", callback_data="dlvideo_format"),
                InlineKeyboardButton("🎵 Audio (MP3/M4A)", callback_data="dlaudio_format")
            ]
        ])
        
        await update.message.reply_text(
            "🎬 **আপনি ফাইলটি কী ফরমেটে ডাউনলোড করতে চান?**\n\nনিচের যেকোনো একটি ফরমেট নির্বাচন করুন:",
            reply_markup=format_keyboard,
            parse_mode="Markdown"
        )

# ==================== MEDIA DOWNLOADER PROCESSOR ====================
async def process_media_download(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type: str):
    query = update.callback_query
    user_id = query.from_user.id
    url = context.user_data.get('pending_url')

    if not url:
        await context.bot.send_message(chat_id=user_id, text="❌ লিংক খুঁজে পাওয়া যায়নি! আবার চেষ্টা করুন।")
        return

    add_user(user_id, query.from_user.username or query.from_user.first_name)

    format_label = "ভিডিও" if format_type == "video" else "অডিও"

    status_msg = await context.bot.send_message(
        chat_id=user_id,
        text=f"🔄 [⚙️       ] **০%** - {format_label} অ্যানালাইজ করা হচ্ছে..."
    )

    async def update_animation():
        frames = [
            f"⏳ [██▒▒▒▒▒▒▒▒] **২০%** {format_label} লিংক প্রসেস করা হচ্ছে...",
            f"⏳ [████▒▒▒▒▒▒] **৪০%** সার্ভারে কানেক্ট করা হচ্ছে...",
            f"⏳ [██████▒▒▒▒] **৬০%** {format_label} স্ট্রিম খোঁজা হচ্ছে...",
            "⏳ [████████▒▒] **৮০%** ফাইল প্রসেস করা হচ্ছে...",
            "📤 [██████████] **১০০%** বটে ফাইল আপলোড হচ্ছে..."
        ]
        for frame in frames:
            await asyncio.sleep(1.2)
            try: 
                await status_msg.edit_text(frame, parse_mode="Markdown")
            except Exception: 
                pass

    anim_task = asyncio.create_task(update_animation())

    filename = None
    try:
        def check_and_download():
            out_tmpl = f"downloads/{user_id}_%(id)s.%(ext)s"
            
            # 🛠️ Fixed Options for yt-dlp
            ydl_opts_dl = {
                'outtmpl': out_tmpl,
                'quiet': True,
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'nocheckcertificate': True,
                'ignoreerrors': False,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'mweb', 'web_creator'],
                    }
                }
            }

            # 🍪 Cookies Support Check
            if os.path.exists("cookies.txt"):
                ydl_opts_dl['cookiefile'] = "cookies.txt"

            # 🛠️ Format fix for YouTube Shorts & normal videos
            if format_type == "video":
                ydl_opts_dl['format'] = 'b/bestvideo+bestaudio/best'
            else:
                ydl_opts_dl['format'] = 'bestaudio/best'

            with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl_dl:
                dl_info = ydl_dl.extract_info(url, download=True)
                fn = ydl_dl.prepare_filename(dl_info)
                return fn, dl_info.get('title', 'Media')

        filename, title = await asyncio.to_thread(check_and_download)
        anim_task.cancel()

        await status_msg.edit_text(f"📤 **{format_label} প্রস্তুত! পাঠানো হচ্ছে...**", parse_mode="Markdown")

        with open(filename, 'rb') as mf:
            if format_type == "video":
                await context.bot.send_video(
                    chat_id=user_id,
                    video=mf,
                    caption=f"✅ **{title}**\n\n🤖 Powered by @itsAdminRimon",
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_audio(
                    chat_id=user_id,
                    audio=mf,
                    caption=f"🎵 **{title}**\n\n🤖 Powered by @itsAdminRimon",
                    parse_mode="Markdown"
                )

        increment_download(user_id)

        if filename and os.path.exists(filename): 
            os.remove(filename)
        await status_msg.delete()

    except Exception as e:
        anim_task.cancel()
        await status_msg.edit_text(f"❌ **ডাউনলোড ব্যর্থ হয়েছে!**\n\nকারণ: `{str(e)}`", parse_mode="Markdown")
        if filename and os.path.exists(filename):
            os.remove(filename)

# ==================== MAIN FUNCTION ====================
def main():
    threading.Thread(target=run_web_server, daemon=True).start()

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0)
    bot_app = Application.builder().token(BOT_TOKEN).request(request).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 প্রফেশনাল টেলিগ্রাম বট সম্পূর্ণ প্রস্তুত...")
    bot_app.run_polling()

if __name__ == "__main__":
    main()
