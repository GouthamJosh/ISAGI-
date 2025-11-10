#CREDITS TO @im_goutham_josh

import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
    LinkPreviewOptions,
)
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.errors.exceptions.bad_request_400 import MessageNotModified
from mfinder.db.files_sql import (
    get_filter_results,
    get_file_details,
    get_precise_filter_results,
)
from mfinder.db.settings_sql import get_search_settings, get_admin_settings
from mfinder.db.ban_sql import is_banned
from mfinder.db.filters_sql import is_filter
from mfinder import LOGGER, ADMINS


# 🔹 In-memory ForceSub configuration (not in DB)
FORCE_SUB_ENABLED = False
FORCE_SUB_CHANNELS = ["-1002544102492"]  # Example: ["-1001234567890", "-1009876543210"]


# --- ADMIN COMMANDS FOR FSUB ---

@Client.on_message(filters.command("fsub") & filters.user(ADMINS))
async def manage_fsub(bot, message):
    """Handle admin commands for managing ForceSub"""
    global FORCE_SUB_ENABLED, FORCE_SUB_CHANNELS

    args = message.text.split(maxsplit=2)

    if len(args) == 1:
        await message.reply_text(
            f"📢 **Force-Subscribe System**\n\n"
            f"**Status:** {'✅ ON' if FORCE_SUB_ENABLED else '❌ OFF'}\n"
            f"**Channels:** `{', '.join(FORCE_SUB_CHANNELS) if FORCE_SUB_CHANNELS else 'None'}`\n\n"
            f"**Commands:**\n"
            f"`/fsub on` - Enable ForceSub\n"
            f"`/fsub off` - Disable ForceSub\n"
            f"`/fsub add <channel_id>` - Add a channel\n"
            f"`/fsub remove <channel_id>` - Remove a channel\n"
            f"`/fsub list` - Show channel list",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    cmd = args[1].lower()

    if cmd == "on":
        FORCE_SUB_ENABLED = True
        await message.reply_text("✅ Force-Subscribe has been *enabled*.")
    elif cmd == "off":
        FORCE_SUB_ENABLED = False
        await message.reply_text("❌ Force-Subscribe has been *disabled*.")
    elif cmd == "add" and len(args) == 3:
        ch_id = args[2]
        if ch_id not in FORCE_SUB_CHANNELS:
            FORCE_SUB_CHANNELS.append(ch_id)
            await message.reply_text(f"✅ Added channel `{ch_id}` to ForceSub list.", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(f"⚠️ Channel `{ch_id}` is already in the list.", parse_mode=ParseMode.MARKDOWN)
    elif cmd == "remove" and len(args) == 3:
        ch_id = args[2]
        if ch_id in FORCE_SUB_CHANNELS:
            FORCE_SUB_CHANNELS.remove(ch_id)
            await message.reply_text(f"❎ Removed channel `{ch_id}` from ForceSub list.", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(f"⚠️ Channel `{ch_id}` not found in the list.", parse_mode=ParseMode.MARKDOWN)
    elif cmd == "list":
        if FORCE_SUB_CHANNELS:
            text = "**📢 ForceSub Channel List:**\n" + "\n".join([f"`{x}`" for x in FORCE_SUB_CHANNELS])
        else:
            text = "⚠️ No ForceSub channels added."
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply_text("❓ Invalid syntax. Use `/fsub` to view commands.")


# --- MAIN MESSAGE HANDLER ---

@Client.on_message(filters.group | filters.private & filters.text & filters.incoming)
async def give_filter(bot, message):
    await filter_(bot, message)


@Client.on_message(~filters.regex(r"^\/") & filters.text & filters.private & filters.incoming)
async def filter_(bot, message):
    user_id = message.from_user.id

    # Ignore prefixed messages (commands/emojis)
    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    # Banned users
    if await is_banned(user_id):
        await message.reply_text("🚫 You are banned. You can't use this bot.", quote=True)
        return

    # 🔹 (ForceSub check removed from here) 🔹

    # 🔹 Repair Mode
    admin_settings = await get_admin_settings()
    if admin_settings and admin_settings.get("repair_mode"):
        return

    # 🔹 Custom Filter
    fltr = await is_filter(message.text)
    if fltr:
        await message.reply_text(text=fltr.message, quote=True)
        return

    # 🔹 Search
    if 2 < len(message.text) < 100:
        search = message.text
        page_no = 1
        me = bot.me
        username = me.username
        result, btn = await get_result(search, page_no, user_id, username)

        if result:
            reply = await message.reply_text(
                f"{result}",
                reply_markup=InlineKeyboardMarkup(btn),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                quote=True,
            )
            asyncio.create_task(delete_after(reply, message, 600))
        else:
            reply = await message.reply_text(
                text="No results found.\nTry again with correct spelling 🤐",
                quote=True,
            )
            asyncio.create_task(delete_after(reply, message, 30))


# --- REFRESH CHECK BUTTON ---

@Client.on_callback_query(filters.regex("^refresh_check$"))
async def refresh_check(bot, query):
    """Recheck after user claims to have joined all channels"""
    user_id = query.from_user.id
    not_joined = []

    for channel_id in FORCE_SUB_CHANNELS:
        try:
            user = await bot.get_chat_member(int(channel_id), user_id)
            if user.status not in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ]:
                not_joined.append(channel_id)
        except Exception:
            not_joined.append(channel_id)

    if not_joined:
        await query.answer("❌ You haven’t joined all channels yet!", show_alert=True)
    else:
        await query.answer("✅ Verified! You can now use the bot.", show_alert=True)
        await query.message.delete()


# --- PAGINATION HANDLER ---

@Client.on_callback_query(filters.regex(r"^(nxt_pg|prev_pg) \d+ \d+ .+$"))
async def pages(bot, query):
    user_id = query.from_user.id
    org_user_id, page_no, search = query.data.split(maxsplit=3)[1:]
    org_user_id = int(org_user_id)
    page_no = int(page_no)
    me = bot.me
    username = me.username

    result, btn = await get_result(search, page_no, user_id, username)
    if result:
        try:
            await query.message.edit(
                f"{result}",
                reply_markup=InlineKeyboardMarkup(btn),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except MessageNotModified:
            pass
    else:
        await query.message.reply_text(
            text="No results found.\nTry again with correct spelling 🤐",
            quote=True,
        )


# --- SEARCH RESULT GENERATOR ---

async def get_result(search, page_no, user_id, username):
    search_settings = await get_search_settings(user_id)

    if search_settings:
        if search_settings.get("precise_mode"):
            files, count = await get_precise_filter_results(query=search, page=page_no)
            precise_search = "Enabled"
        else:
            files, count = await get_filter_results(query=search, page=page_no)
            precise_search = "Disabled"
    else:
        files, count = await get_filter_results(query=search, page=page_no)
        precise_search = "Disabled"

    if files:
        btn = []
        index = (page_no - 1) * 10
        crnt_pg = index // 10 + 1
        tot_pg = (count + 10 - 1) // 10
        result = (
            f"**Search Query:** `{search}`\n"
            f"**Total Results:** `{count}`\n"
            f"**Page:** `{crnt_pg}/{tot_pg}`\n"
            f"**Precise Search:** `{precise_search}`\n\n"
            f"🔻 __Tap below to get files.__ 🔻"
        )

        for file in files:
            file_id = file.file_id
            filename = f"[{get_size(file.file_size)}] {file.file_name}"
            btn.append([InlineKeyboardButton(text=filename, url=f"https://t.me/{username}?start={file_id}")])

        if crnt_pg > 1:
            btn.append([InlineKeyboardButton("<< Previous", callback_data=f"prev_pg {user_id} {page_no - 1} {search}")])
        if crnt_pg < tot_pg:
            btn.append([InlineKeyboardButton("Next >>", callback_data=f"nxt_pg {user_id} {page_no + 1} {search}")])

        return result, btn

    return None, None


# --- FILE SENDER (with FSUB check + auto-delete reply) ---

async def send_file(bot, chat_id, file_id):
    # 🔹 ForceSub check
    if FORCE_SUB_ENABLED and FORCE_SUB_CHANNELS:
        not_joined = []
        for channel_id in FORCE_SUB_CHANNELS:
            try:
                user = await bot.get_chat_member(int(channel_id), chat_id)
                if user.status == ChatMemberStatus.BANNED:
                    await bot.send_message(chat_id, "🚫 You are banned from one of the required channels.")
                    return
            except UserNotParticipant:
                not_joined.append(channel_id)
            except Exception as e:
                LOGGER.warning(f"ForceSub error for {channel_id}: {e}")

        if not_joined:
            buttons = []
            for ch_id in not_joined:
                try:
                    chat = await bot.get_chat(int(ch_id))
                    link = chat.invite_link or await chat.export_invite_link()
                    btn = InlineKeyboardButton(f"📢 Join {chat.title}", url=link)
                except Exception:
                    link = f"https://t.me/{str(ch_id).replace('-100', '')}"
                    btn = InlineKeyboardButton("📢 Join Channel", url=link)
                buttons.append([btn])
            buttons.append([InlineKeyboardButton("✅ Joined All", callback_data="refresh_check")])

            await bot.send_message(
                chat_id,
                "**Please join all required update channels to get the file!**",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # 🔹 Proceed with file sending
    filedetails = await get_file_details(file_id)
    admin_settings = await get_admin_settings()
    for files in filedetails:
        f_caption = files.caption or f"{files.file_name}"

        if admin_settings.get("custom_caption"):
            f_caption = admin_settings.get("custom_caption")

        f_caption = "`" + f_caption + "`"
        if admin_settings.get("caption_uname"):
            f_caption += "\n" + admin_settings.get("caption_uname")

        # Send the file
        msg = await bot.send_cached_media(
            chat_id=chat_id,
            file_id=file_id,
            caption=f_caption,
            parse_mode=ParseMode.MARKDOWN,
        )

        # 🔹 Send auto-delete info message
        if admin_settings.get("auto_delete"):
            delay_dur = admin_settings.get("auto_delete")
            notify = await bot.send_message(
                chat_id,
                f"📁 File sent! This message and file will auto-delete in {delay_dur} seconds ⏳",
            )
            await asyncio.sleep(delay_dur)
            try:
                await msg.delete()
                await notify.delete()
            except Exception as e:
                LOGGER.warning(f"Failed to auto-delete: {e}")

# --- FILE CALLBACK ---

@Client.on_callback_query(filters.regex(r"^file (.+)$"))
async def get_files(bot, query):
    user_id = query.from_user.id
    file_id = query.data.split()[1]
    await query.answer("📤 Sending file...", cache_time=60)
    await send_file(bot, user_id, file_id)


# --- /START HANDLER ---

@Client.on_message(filters.private & filters.command("start"))
async def start(bot, message):
    if len(message.command) > 1:
        file_id = message.command[1]
        await send_file(bot, message.from_user.id, file_id)
    else:
        await message.reply_text("👋 Welcome! Send me a movie or file name to search.")


# --- UTILITIES ---

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"


async def delete_after(bot_msg, user_msg, delay):
    await asyncio.sleep(delay)
    try:
        await bot_msg.delete()
        await user_msg.delete()
    except Exception as e:
        LOGGER.warning(f"Failed to delete messages: {e}")
