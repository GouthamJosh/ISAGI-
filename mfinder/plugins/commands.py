# CREDITS TO @im_goutham_josh

import os
import sys
import asyncio
import time
import shutil
from psutil import cpu_percent, virtual_memory, disk_usage
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from mfinder.db.broadcast_sql import add_user
from mfinder.utils.constants import STARTMSG, HELPMSG, SET_MSG
from mfinder import LOGGER, ADMINS, START_MSG, HELP_MSG, START_KB, HELP_KB
from mfinder.utils.util_support import humanbytes, get_db_size
from mfinder.plugins.serve import send_file  # ✅ deep-linking fix

from pymongo import UpdateMany
from mfinder.db.settings_sql import (
    get_search_settings,
    change_search_settings,
    SETTINGS_COLLECTION,
    INSERTION_LOCK,
)

# =========================================================
# /start Command — handles both normal start and deep link
# =========================================================
@Client.on_message(filters.command(["start"]))
async def start(bot, message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "User"
    user_name = f"@{message.from_user.username}" if message.from_user.username else None
    await add_user(user_id, user_name)

    # Normal /start
    if len(message.command) == 1:
        try:
            start_msg = START_MSG.format(name, user_id)
        except Exception as e:
            LOGGER.warning(e)
            start_msg = STARTMSG.format(name, user_id)

        await bot.send_message(
            chat_id=message.chat.id,
            text=start_msg,
            reply_markup=START_KB,
        )

        # Apply default settings for new users
        search_settings = await get_search_settings(user_id)
        if not search_settings:
            await change_search_settings(user_id, link_mode=True)

    # Deep link /start <file_id>
    elif len(message.command) == 2:
        file_id = message.command[1]
        await send_file(bot, user_id, file_id)


# =========================================================
# /help Command
# =========================================================
@Client.on_message(filters.command(["help"]))
async def help_m(bot, message):
    try:
        help_msg = HELP_MSG
    except Exception as e:
        LOGGER.warning(e)
        help_msg = HELPMSG

    await bot.send_message(
        chat_id=message.chat.id,
        text=help_msg,
        reply_markup=HELP_KB,
    )


# =========================================================
# Callback: Back and Help buttons
# =========================================================
@Client.on_callback_query(filters.regex(r"^back_m$"))
async def back(bot, query):
    user_id = query.from_user.id
    name = query.from_user.first_name or "User"
    try:
        start_msg = START_MSG.format(name, user_id)
    except Exception as e:
        LOGGER.warning(e)
        start_msg = STARTMSG.format(name, user_id)

    await query.message.edit_text(start_msg, reply_markup=START_KB)


@Client.on_callback_query(filters.regex(r"^help_cb$"))
async def help_cb(bot, query):
    try:
        help_msg = HELP_MSG
    except Exception as e:
        LOGGER.warning(e)
        help_msg = HELPMSG

    await query.message.edit_text(help_msg, reply_markup=HELP_KB)


# =========================================================
# /restart Command (Admin only)
# =========================================================
@Client.on_message(filters.command(["restart"]) & filters.user(ADMINS))
async def restart(bot, message):
    LOGGER.warning("Restarting bot using /restart command...")
    msg = await message.reply_text("__Restarting...__")
    await asyncio.sleep(1)
    await msg.edit("__Bot restarted!__")
    os.execv(sys.executable, ["python3", "-m", "mfinder"] + sys.argv)


# =========================================================
# /logs Command (Admin only)
# =========================================================
@Client.on_message(filters.command(["logs"]) & filters.user(ADMINS))
async def log_file(bot, message):
    try:
        await message.reply_document("logs.txt", caption="📜 Bot Logs")
    except Exception as e:
        await message.reply_text(f"⚠️ Error: {e}")


# =========================================================
# /server Command (Admin only)
# =========================================================
@Client.on_message(filters.command(["server"]) & filters.user(ADMINS))
async def server_stats(bot, message):
    sts = await message.reply_text("__Calculating server stats...__")

    # 🕒 Measure ping
    start_t = time.time()
    await bot.get_me()
    end_t = time.time()
    ping = f"{(end_t - start_t) * 1000:.2f} ms"

    total, used, free = shutil.disk_usage(".")
    ram = virtual_memory()
    cpu_usage = cpu_percent()
    ram_usage = ram.percent
    used_disk = disk_usage("/").percent
    db_size = get_db_size()

    stats_msg = (
        f"**🤖 BOT STATS**\n"
        f"`Ping:` {ping}\n\n"
        f"**💾 SERVER DETAILS**\n"
        f"`Disk:` {humanbytes(total)} total | {humanbytes(used)} used | {humanbytes(free)} free\n"
        f"`Disk Usage:` {used_disk}%\n"
        f"`RAM:` {humanbytes(ram.total)} total | {humanbytes(ram.used)} used\n"
        f"`RAM Usage:` {ram_usage}%\n"
        f"`CPU Usage:` {cpu_usage}%\n\n"
        f"**🗃 DATABASE**\n"
        f"`Size:` {db_size} MB"
    )

    await sts.edit(stats_msg)
