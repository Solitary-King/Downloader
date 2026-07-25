import os
import sqlite3
import logging
import asyncio
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

# Downloads ডিরেক্টরি নিশ্চিতকরণ
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8914943378:AAH5uJ-IZYZa6ighXT1OUxglfGFKkPnwKm4"  # আপনার বট টোকেন দিন
ADMIN_ID = 6535070545  # আপনার টেলিগ্রাম Numeric ID দিন
DB_NAME = "bot_data.db"

logging.basicConfig(level=logging.INFO)

# Menu Button Texts
MENU_BUTTONS = ["👤 Profile", "👥 Refer", "📥 Download Video", "💎 Premium Pack", "👑 Admin Panel"]

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            coins INTEGER DEFAULT 0,
            referred_by INTEGER,
            ref_completed INTEGER DEFAULT 0,
            total_downloads INTEGER DEFAULT 0,
            max_download_limit INTEGER DEFAULT 20
        )
    ''')
    
    # Channels Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_url TEXT
        )
    ''')
    
    # Packages Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS packages (
            pack_name TEXT PRIMARY KEY,
            size_mb INTEGER,
            cost_coins INTEGER
        )
    ''')
    
    # Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    
    # Default Values
    cursor.execute("INSERT OR IGNORE INTO packages VALUES ('50MB', 50, 10)")
    cursor.execute("INSERT OR IGNORE INTO packages VALUES ('100MB', 100, 20)")
    cursor.execute("INSERT OR IGNORE INTO packages VALUES ('150MB', 150, 30)")
    cursor.execute("INSERT OR IGNORE INTO packages VALUES ('200MB', 200, 40)")
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('refer_coins', 3)")
    
    conn.commit()
    conn.close()

init_db()

# ==================== DATABASE HELPERS ====================
def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, referred_by=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        uname = username if username else "NoUsername"
        cursor.execute(
            "INSERT INTO users (user_id, username, referred_by, ref_completed) VALUES (?, ?, ?, 0)",
            (user_id, uname, referred_by)
        )
        conn.commit()
    conn.close()

def get_refer_coins():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'refer_coins'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 3

def set_refer_coins_db(coins):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('refer_coins', ?)", (coins,))
    conn.commit()
    conn.close()

# 🔔 রেফার সম্পন্ন হওয়ার পর নোটিফিকেশন পাঠানোর ফাংশন
async def complete_referral(user_id, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT referred_by, ref_completed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] and row[1] == 0:
        referrer_id = row[0]
        ref_coins = get_refer_coins()
        cursor.execute("UPDATE users SET ref_completed = 1 WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (ref_coins, referrer_id))
        conn.commit()
        conn.close()

        # রেফারারকে নোটিফিকেশন পাঠানো
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 **নতুন সফল রেফারেল!**\n\n"
                    f"একজন নতুন ইউজার আপনার রেফারেল লিংক ব্যবহার করে জয়েন করেছেন।\n"
                    f"💰 আপনি পেয়েছেন: **+{ref_coins} Coins**"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Referral Notification Error: {e}")
    else:
        conn.close()

def update_user_coins(user_id, coins):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = ? WHERE user_id = ?", (coins, user_id))
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

def get_packages():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT pack_name, size_mb, cost_coins FROM packages")
    packs = cursor.fetchall()
    conn.close()
    return packs

def set_package_price(pack_name, cost_coins):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE packages SET cost_coins = ? WHERE pack_name = ?", (cost_coins, pack_name))
    conn.commit()
    conn.close()

def update_user_limit(user_id, new_limit, cost):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET max_download_limit = ?, coins = coins - ? WHERE user_id = ?", (new_limit, cost, user_id))
    conn.commit()
    conn.close()

def increment_download(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_downloads) FROM users")
    total_dl = cursor.fetchone()[0] or 0
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
        [KeyboardButton("👤 Profile"), KeyboardButton("👥 Refer")],
        [KeyboardButton("📥 Download Video"), KeyboardButton("💎 Premium Pack")]
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
    context.user_data.clear() # Clear state on start
    user = update.effective_user
    args = context.args
    referrer = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user.id else None

    add_user(user.id, user.username or user.first_name, referrer)

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

    await complete_referral(user.id, context)

    await update.message.reply_text(
        f"👋 **স্বাগতম {user.first_name}!**\n\nনিচের বাটনগুলো থেকে আপনার পছন্দ অনুযায়ী সার্ভিস বেছে নিন এবং সোশ্যাল মিডিয়ার যেকোনো ভিডিও/অডিও ডাউনলোড করুন:",
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
            await complete_referral(user_id, context)
            
            try:
                await query.message.delete()
            except Exception:
                pass
                
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ **অভিনন্দন! আপনার ভেরিফিকেশন সফল হয়েছে।**\n\nএখন নিচের মেনু থেকে অপশন বেছে নিন:",
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

    elif data.startswith("buy_"):
        _, size, cost = data.split("_")
        size, cost = int(size), int(cost)
        u = get_user(user_id)

        if u[2] < cost:
            await query.answer("❌ আপনার পর্যাপ্ত কয়েন নেই! রেফার করে কয়েন আয় করুন।", show_alert=True)
            return

        update_user_limit(user_id, size, cost)
        await query.answer("🎉 প্রিমিয়াম প্যাক অ্যাক্টিভ হয়েছে!", show_alert=True)
        await query.message.reply_text(
            f"✅ **প্রিমিয়াম প্যাক কেনা সফল হয়েছে!**\n\nআপনার নতুন ডাউনলোড লিমিট: **{size} MB**",
            reply_markup=main_reply_keyboard(user_id),
            parse_mode="Markdown"
        )

    # ADMIN BUTTON ACTIONS
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

        elif data == "adm_setpack":
            context.user_data['state'] = 'SET_PACK_NAME'
            await query.message.reply_text("✍️ প্যাকের নাম লিখুন (যেমন: `50MB`, `100MB`, `150MB`, `200MB`):")

        elif data == "adm_setcoins":
            context.user_data['state'] = 'SET_USER_ID'
            await query.message.reply_text("✍️ ইউজারের Telegram Numeric ID দিন যার কয়েন আপডেট করবেন:")

        elif data == "adm_setref":
            context.user_data['state'] = 'SET_REF_COINS'
            await query.message.reply_text("✍️ প্রতি সফল রেফারে ইউজার কত কয়েন বোনাস পাবে তা লিখুন (যেমন: 5 বা 10):")

        elif data == "adm_bcast":
            context.user_data['state'] = 'BROADCAST'
            await query.message.reply_text("📢 সকল ইউজারের কাছে যে মেসেজ পাঠাতে চান তা লিখুন:")

# ==================== TEXT MESSAGES & STATE HANDLER ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = context.user_data.get('state', None)

    # 1. MENU BUTTON RESET
    if text in MENU_BUTTONS:
        context.user_data.clear()
        
        if text == "👤 Profile":
            u = get_user(user_id)
            if not u:
                await update.message.reply_text("❌ প্রোফাইল ডেটা পাওয়া যায়নি! অনুগ্রহ করে /start দিন।")
                return

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ? AND ref_completed = 1", (user_id,))
            ref_count = c.fetchone()[0]
            conn.close()

            username_display = f"@{u[1]}" if u[1] and u[1] not in ["None", "NoUsername"] else "ইউজারনেম সেট করা নেই"

            profile_msg = (
                f"👤 **আপনার প্রোফাইল**\n\n"
                f"🆔 **ইউজার আইডি:** `{u[0]}`\n"
                f"👤 **ইউজারনেম:** {username_display}\n"
                f"💰 **কয়েন ব্যালেন্স:** {u[2]} Coins\n"
                f"⚡ **ডাউনলোড লিমিট:** {u[6]} MB\n"
                f"👥 **সফল রেফার:** {ref_count}\n"
                f"📥 **মোট ডাউনলোড:** {u[5]}"
            )
            await update.message.reply_text(profile_msg, parse_mode="Markdown")
            return

        elif text == "👥 Refer":
            bot_username = (await context.bot.get_me()).username
            refer_link = f"https://t.me/{bot_username}?start={user_id}"
            ref_coins = get_refer_coins()
            refer_msg = (
                f"👥 **রেফার করে কয়েন আয় করুন!**\n\n"
                f"আপনার ইনভাইট লিংক দিয়ে বন্ধুদের জয়েন করান। তারা বট চালু করে চ্যানেলে **জয়েন সম্পন্ন করলেই** আপনি পাবেন **{ref_coins} কয়েন**!\n\n"
                f"🔗 **আপনার ইউনিক রেফারেল লিংক:**\n`{refer_link}`"
            )
            await update.message.reply_text(refer_msg, parse_mode="Markdown")
            return

        elif text == "📥 Download Video":
            await update.message.reply_text(
                "👇 **নিচে থেকে প্ল্যাটফর্ম নির্বাচন করে আপনার ভিডিও ডাউনলোড করে নিন:**",
                reply_markup=platform_inline_keyboard(),
                parse_mode="Markdown"
            )
            return

        elif text == "💎 Premium Pack":
            packs = get_packages()
            u = get_user(user_id)
            msg = f"💎 **প্রিমিয়াম প্যাক সার্ভিস**\n\nবর্তমান লিমিট: **{u[6]} MB**\nবর্তমান কয়েন ব্যালেন্স: **{u[2]} Coins**\n\nকয়েন খরচ করে আপনার ডাউনলোডের এমবি লিমিট বাড়িয়ে নিন:\n\n"
            
            keyboard = []
            for name, size, cost in packs:
                msg += f"🔹 **{name} প্যাক:** {size} MB সাইজ পর্যন্ত ডাউনলোড ➡️ **{cost} Coins**\n"
                keyboard.append([InlineKeyboardButton(f"⚡ Buy {name} ({cost} Coins)", callback_data=f"buy_{size}_{cost}")])
                
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        elif text == "👑 Admin Panel" and user_id == ADMIN_ID:
            ref_coins = get_refer_coins()
            admin_kbd = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Broadcast", callback_data="adm_bcast"), InlineKeyboardButton("📊 User Stats", callback_data="adm_stats")],
                [InlineKeyboardButton("➕ Add Channel", callback_data="adm_addch"), InlineKeyboardButton("🗑️ Remove Channel", callback_data="adm_remch")],
                [InlineKeyboardButton("📜 List Channels", callback_data="adm_listch"), InlineKeyboardButton("⚙️ Set Pack Price", callback_data="adm_setpack")],
                [InlineKeyboardButton("💰 Modify User Coins", callback_data="adm_setcoins"), InlineKeyboardButton(f"🎁 Set Refer Coins ({ref_coins})", callback_data="adm_setref")]
            ])
            await update.message.reply_text("👑 **এডমিন কন্ট্রোল প্যানেল**\n\nনিচের অপশনগুলো দিয়ে বট পরিচালনা করুন:", reply_markup=admin_kbd, parse_mode="Markdown")
            return

    # 2. ADMIN STATE PROCESSOR
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

        elif state == 'SET_REF_COINS':
            if text.isdigit():
                set_refer_coins_db(int(text))
                await update.message.reply_text(f"🎁 **সফল হয়েছে!** নতুন রেফারেল বোনাস **{text} Coins** সেট করা হয়েছে।", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ অনুগ্রহ করে সঠিক সংখ্যা প্রদান করুন।")
            context.user_data.clear()
            return

        elif state == 'SET_USER_ID':
            if text.isdigit():
                context.user_data['target_uid'] = int(text)
                context.user_data['state'] = 'SET_USER_COINS'
                await update.message.reply_text(f"✍️ ইউজার `{text}` এর জন্য নতুন কয়েন ব্যালেন্স লিখুন:")
            else:
                await update.message.reply_text("❌ সঠিক Telegram ID দিন!")
                context.user_data.clear()
            return

        elif state == 'SET_USER_COINS':
            if text.isdigit():
                t_uid = context.user_data.get('target_uid')
                update_user_coins(t_uid, int(text))
                await update.message.reply_text(f"✅ ইউজার `{t_uid}` এর ব্যালেন্স **{text} Coins** আপডেট করা হয়েছে!", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন!")
            context.user_data.clear()
            return

        elif state == 'SET_PACK_NAME':
            context.user_data['pack_name'] = text.upper()
            context.user_data['state'] = 'SET_PACK_COST'
            await update.message.reply_text(f"✍️ **{text.upper()}** প্যাকের নতুন মূল্য (কয়েনে) লিখুন:")
            return

        elif state == 'SET_PACK_COST':
            if text.isdigit():
                p_name = context.user_data.get('pack_name')
                set_package_price(p_name, int(text))
                await update.message.reply_text(f"✅ **{p_name}** প্যাকের দাম **{text} Coins** আপডেট করা হয়েছে!", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন!")
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

    # 3. FORCE JOIN CHECK
    not_joined = await check_force_join(user_id, context)
    if not_joined:
        await update.message.reply_text("⚠️ আপনাকে অবশ্যই প্রথমে চ্যানেলে জয়েন করতে হবে! /start দিন।")
        return

    # 4. DOWNLOAD LINK OPTION SELECTION
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

    u = get_user(user_id)
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
            ydl_opts_info = {
                'quiet': True,
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.tiktok.com/',
                'extractor_args': {'tiktok': {'webpage_download': True, 'app_version': '30.0.0'}}
            }
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                filesize = info.get('filesize') or info.get('filesize_approx') or 0
                max_allowed_bytes = u[6] * 1024 * 1024

                if filesize > max_allowed_bytes:
                    video_mb = round(filesize / (1024 * 1024), 2)
                    return None, f"LIMIT_EXCEEDED_{video_mb}", info.get('title', 'Media')

                if format_type == "video":
                    out_tmpl = f"downloads/{user_id}_%(id)s.%(ext)s"
                    ydl_opts_dl = {
                        'format': 'best[ext=mp4]/best',
                        'outtmpl': out_tmpl,
                        'quiet': True,
                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'referer': 'https://www.tiktok.com/',
                        'extractor_args': {'tiktok': {'webpage_download': True, 'app_version': '30.0.0'}}
                    }
                else: # Audio Configuration (FFmpeg ছাড়া সেফ অডিও ডাউনলোড)
                    out_tmpl = f"downloads/{user_id}_%(id)s.%(ext)s"
                    ydl_opts_dl = {
                        'format': 'bestaudio/best',
                        'outtmpl': out_tmpl,
                        'quiet': True,
                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'referer': 'https://www.tiktok.com/',
                    }

                with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl_dl:
                    dl_info = ydl_dl.extract_info(url, download=True)
                    fn = ydl_dl.prepare_filename(dl_info)
                    return fn, "SUCCESS", dl_info.get('title', 'Media')

        filename, status, title = await asyncio.to_thread(check_and_download)
        anim_task.cancel()

        if status.startswith("LIMIT_EXCEEDED"):
            video_mb = status.split("_")[2]
            await status_msg.edit_text(
                f"⚠️ **ফাইল সাইজ লিমিট অতিক্রম করেছে!**\n\n"
                f"📽️ এই ফাইলের সাইজ: **{video_mb} MB**\n"
                f"🔒 আপনার ডাউনলোড লিমিট: **{u[6]} MB**\n\n"
                f"💡 প্রিমিয়াম প্যাক কিনে সীমানা বাড়াতে '💎 Premium Pack' অপশনটি বেছে নিন।",
                parse_mode="Markdown"
            )
            return

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
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0)

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 প্রফেশনাল টেলিগ্রাম বট সম্পূর্ণ প্রস্তুত...")
    app.run_polling()

if __name__ == "__main__":
    main()
