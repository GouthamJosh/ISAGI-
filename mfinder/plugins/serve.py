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
from mfinder import LOGGER


# 🔹 Multiple channel IDs separated by spaces
# Example: AUTH_CHANNEL="-1001234567890 -1002222222222 -1003333333333"
AUTH_CHANNELS = os.getenv("AUTH_CHANNEL", "-1002544102492").split()


@Client.on_message(filters.group | filters.private & filters.text & filters.incoming)
async def give_filter(bot, message):
    await filter_(bot, message)


@Client.on_message(~filters.regex(r"^\/") & filters.text & filters.private & filters.incoming)
async def filter_(bot, message):
    user_id = message.from_user.id

    # Ignore prefixed commands
    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    # Check banned
    if await is_banned(user_id):
        await message.reply_text("You are banned. You can't use this bot.", quote=True)
        return

    # 🔹 Multi Force Sub Check (ENV)
    if AUTH_CHANNELS:
        not_joined = []
        for channel_id in AUTH_CHANNELS:
            try:
                user = await bot.get_chat_member(int(channel_id), user_id)
                if user.status == ChatMemberStatus.BANNED:
                    await message.reply_text("Sorry, you are banned from one of the channels.", quote=True)
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
            await message.reply_text(
                "**Please join all update channels to use this Bot!**",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
                quote=True,
            )
            return

    # 🔹 Repair Mode
    admin_settings = await get_admin_settings()
    if admin_settings and admin_settings.get("repair_mode"):
        return

    # 🔹 Check Custom Filter
    fltr = await is_filter(message.text)
    if fltr:
        await message.reply_text(text=fltr.message, quote=True)
        return

    # 🔹 Search logic
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
                text="No results found.\nOr retry with the correct spelling 🤐",
                quote=True,
            )
            asyncio.create_task(delete_after(reply, message, 30))


# 🔹 Refresh check when user clicks “✅ Joined All”
@Client.on_callback_query(filters.regex("^refresh_check$"))
async def refresh_check(bot, query):
    user_id = query.from_user.id
    not_joined = []
    for channel_id in AUTH_CHANNELS:
        try:
            user = await bot.get_chat_member(int(channel_id), user_id)
            if user.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                not_joined.append(channel_id)
        except Exception:
            not_joined.append(channel_id)

    if not_joined:
        await query.answer("You haven't joined all channels yet ❌", show_alert=True)
    else:
        await query.answer("✅ Verified! You can now use the bot.", show_alert=True)
        await query.message.delete()


# 🔹 Rest of the original functions stay same
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
            text="No results found.\nOr retry with the correct spelling 🤐",
            quote=True,
        )


# (get_result, send_file, get_files, start, get_size, delete_after) remain same


# ======================================================
# 🔍 File Search Function
# ======================================================
async def get_result(search, page_no, user_id, username):
    search_settings = await get_search_settings(user_id)

    if search_settings and search_settings.get("precise_mode"):
        files, count = await get_precise_filter_results(query=search, page=page_no)
        precise_search = "Enabled"
    else:
        files, count = await get_filter_results(query=search, page=page_no)
        precise_search = "Disabled"

    if not files:
        return None, None

    btn = []
    index = (page_no - 1) * 10
    crnt_pg = index // 10 + 1
    tot_pg = (count + 9) // 10

    result = (
        f"**Search Query:** `{search}`\n"
        f"**Total Results:** `{count}`\n"
        f"**Page:** `{crnt_pg}/{tot_pg}`\n"
        f"**Precise Search:** `{precise_search}`\n"
        f"**Result Mode:** `Button`\n\n"
        "🔻 __Tap a file below to download.__ 🔻"
    )

    for file in files:
        file_id = file.file_id
        filename = f"[{get_size(file.file_size)}] {file.file_name}"
        btn.append(
            [InlineKeyboardButton(text=filename, url=f"https://t.me/{username}?start={file_id}")]
        )

    # Pagination buttons
    kb = []
    if crnt_pg == 1 and tot_pg > 1:
        kb = [InlineKeyboardButton("Next >>", callback_data=f"nxt_pg {user_id} {page_no + 1} {search}")]
    elif 1 < crnt_pg < tot_pg:
        kb = [
            InlineKeyboardButton("<< Previous", callback_data=f"prev_pg {user_id} {page_no - 1} {search}"),
            InlineKeyboardButton("Next >>", callback_data=f"nxt_pg {user_id} {page_no + 1} {search}")
        ]
    elif crnt_pg == tot_pg and tot_pg > 1:
        kb = [InlineKeyboardButton("<< Previous", callback_data=f"prev_pg {user_id} {page_no - 1} {search}")]

    if kb:
        btn.append(kb)

    return result, btn


# ======================================================
# 📤 Send File
# ======================================================
async def send_file(bot, chat_id, file_id):
    filedetails = await get_file_details(file_id)
    admin_settings = await get_admin_settings()

    if not filedetails:
        await bot.send_message(chat_id, "❌ File not found.")
        return

    for files in filedetails:
        f_caption = files.caption or f"{files.file_name}"

        if admin_settings.get("custom_caption"):
            f_caption = admin_settings["custom_caption"]

        f_caption = f"`{f_caption}`"

        if admin_settings.get("caption_uname"):
            f_caption += "\n" + admin_settings["caption_uname"]

        msg = await bot.send_cached_media(
            chat_id=chat_id,
            file_id=file_id,
            caption=f_caption,
            parse_mode=ParseMode.MARKDOWN,
        )

        # Auto delete feature
        if admin_settings.get("auto_delete"):
            delay_dur = admin_settings["auto_delete"]
            delay_text = (
                f"{round(delay_dur / 60, 2)} mins" if delay_dur > 60 else f"{delay_dur} secs"
            )

            disc = await bot.send_message(
                chat_id,
                f"⚠️ Save this file — it will be deleted in {delay_text}.",
            )

            await asyncio.sleep(delay_dur)
            try:
                await disc.delete()
                await msg.delete()
                await bot.send_message(chat_id, "🗑 File deleted automatically.")
            except Exception as e:
                LOGGER.warning(f"Auto-delete failed: {e}")


# ======================================================
# 📦 File Callback
# ======================================================
@Client.on_callback_query(filters.regex(r"^file (.+)$"))
async def get_files(bot, query):
    user_id = query.from_user.id
    file_id = query.data.split()[1]
    await query.answer("📤 Sending file...", cache_time=60)
    await send_file(bot, user_id, file_id)


# ======================================================
# 👋 Start Command
# ======================================================
@Client.on_message(filters.private & filters.command("start"))
async def start(bot, message):
    if len(message.command) > 1:
        file_id = message.command[1]
        user_id = message.from_user.id
        await send_file(bot, user_id, file_id)
    else:
        await message.reply_text("👋 Welcome! Send me a search query.")


# ======================================================
# ⚙️ Utilities
# ======================================================
def get_size(size):
    """Convert file size to readable format."""
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"


async def delete_after(bot_msg, user_msg, delay):
    """Delete messages after a given delay."""
    await asyncio.sleep(delay)
    try:
        await bot_msg.delete()
        await user_msg.delete()
    except Exception as e:
        LOGGER.warning(f"Failed to delete messages: {e}")
