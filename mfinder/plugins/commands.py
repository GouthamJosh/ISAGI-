import os
import sys
import asyncio
import time
import shutil
from psutil import cpu_percent, virtual_memory, disk_usage
from pyrogram import Client, filters
from mfinder.db.broadcast_sql import add_user
from mfinder.db.settings_sql import get_search_settings, change_search_settings
from mfinder.utils.constants import STARTMSG, HELPMSG
from mfinder import LOGGER, ADMINS, START_MSG, HELP_MSG, START_KB, HELP_KB
from mfinder.utils.util_support import humanbytes, get_db_size
from mfinder.plugins.serve import send_file  # Updated import to send_file for deep-linking


@Client.on_message(filters.command(["start"]))
async def start(bot, update):
    if len(update.command) == 1:
        user_id = update.from_user.id
        name = update.from_user.first_name if update.from_user.first_name else " "
        user_name = (
            "@" + update.from_user.username if update.from_user.username else None
        )
        await add_user(user_id, user_name)

        try:
            start_msg = START_MSG.format(name, user_id)
        except Exception as e:
            LOGGER.warning(e)
            start_msg = STARTMSG.format(name, user_id)

        await bot.send_message(
            chat_id=update.chat.id,
            text=start_msg,
            reply_to_message_id=update.reply_to_message_id,
            reply_markup=START_KB,
        )
        search_settings = await get_search_settings(user_id)
        if not search_settings:
            # Ensures default search setting is applied if user is new
            await change_search_settings(user_id, link_mode=True)
    elif len(update.command) == 2:
        # Handle deep-linking for file fetching by calling send_file directly
        file_id = update.command[1]
        user_id = update.from_user.id
        await send_file(bot, user_id, file_id)


@Client.on_message(filters.command(["help"]))
async def help_m(bot, update):
    try:
        help_msg = HELP_MSG
    except Exception as e:
        LOGGER.warning(e)
        help_msg = HELPMSG

    await bot.send_message(
        chat_id=update.chat.id,
        text=help_msg,
        reply_to_message_id=update.reply_to_message_id,
        reply_markup=HELP_KB,
    )


@Client.on_callback_query(filters.regex(r"^back_m$"))
async def back(bot, query):
    user_id = query.from_user.id
    name = query.from_user.first_name if query.from_user.first_name else " "
    try:
        start_msg = START_MSG.format(name, user_id)
    except Exception as e:
        LOGGER.warning(e)
        start_msg = STARTMSG.format(name, user_id)  # Use formatted STARTMSG here
    await query.message.edit_text(start_msg, reply_markup=START_KB)


@Client.on_callback_query(filters.regex(r"^help_cb$"))
async def help_cb(bot, query):
    try:
        help_msg = HELP_MSG
    except Exception as e:
        LOGGER.warning(e)
        help_msg = HELPMSG
    await query.message.edit_text(help_msg, reply_markup=HELP_KB)


@Client.on_message(filters.command(["restart"]) & filters.user(ADMINS))
async def restart(bot, update):
    LOGGER.warning("Restarting bot using /restart command")
    msg = await update.reply_text(text="__Restarting.....__")
    # Added a slight delay for user feedback
    await asyncio.sleep(1)
    await msg.edit("__Bot restarted !__")
    # Using sys.executable is safer
    os.execv(sys.executable, ["python3", "-m", "mfinder"] + sys.argv)


@Client.on_message(filters.command(["logs"]) & filters.user(ADMINS))
async def log_file(bot, update):
    logs_msg = await update.reply_text("__Sending logs, please wait...__")
    try:
        await update.reply_document("logs.txt")
    except Exception as e:
        await update.reply_text(str(e))
    await logs_msg.delete()


@Client.on_message(filters.command(["server"]) & filters.user(ADMINS))
async def server_stats(bot, update):
    sts = await update.reply_text("__Calculating, please wait...__")
    
    # Calculate ping more accurately before other operations
    start_t = time.time()
    await update.reply_text("Ping test...")
    end_t = time.time()
    time_taken_s = (end_t - start_t) * 1000
    ping = f"{time_taken_s:.3f} ms"
    
    total, used, free = shutil.disk_usage(".")
    ram = virtual_memory()
    
    total = humanbytes(total)
    used = humanbytes(used)
    free = humanbytes(free)
    t_ram = humanbytes(ram.total)
    u_ram = humanbytes(ram.used)
    f_ram = humanbytes(ram.available)
    cpu_usage = cpu_percent()
    ram_usage = virtual_memory().percent
    used_disk = disk_usage("/").percent
    db_size = get_db_size()

    stats_msg = f"--**BOT STATS**--\n`Ping: {ping}`\n\n--**SERVER DETAILS**--\n`Disk Total/Used/Free: {total}/{used}/{free}\nDisk usage: {used_disk}%\nRAM Total/Used/Free: {t_ram}/{u_ram}/{f_ram}\nRAM Usage: {ram_usage}%\nCPU Usage: {cpu_usage}%`\n\n--**DATABASE DETAILS**--\n`Size: {db_size} MB`"
    try:
        await sts.edit(stats_msg)
    except Exception as e:
        await update.reply_text(str(e))

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from mfinder.db.settings_sql import get_search_settings, change_search_settings
from mfinder.utils.constants import SET_MSG


@Client.on_message(filters.command(["settings"]))
async def user_settings(bot, update):
    user_id = update.from_user.id
    set_kb = await find_search_settings(user_id)
    await bot.send_message(
        chat_id=user_id,
        text=SET_MSG,
        reply_markup=set_kb,
    )


@Client.on_callback_query(filters.regex(r"^prec (.+)$"))
async def set_precise_mode(bot, query):
    user_id = query.from_user.id
    prsc_mode = query.data.split()[1]
    if prsc_mode == "on":
        await change_search_settings(user_id, precise_mode=True)
    if prsc_mode == "off":
        await change_search_settings(user_id, precise_mode=False)
    if prsc_mode == "md":
        await query.answer(text="Toggle Precise Search ON/OFF", show_alert=False)
        return

    set_kb = await find_search_settings(user_id)

    await query.message.edit(
        text=SET_MSG,
        reply_markup=set_kb,
    )


@Client.on_callback_query(filters.regex(r"^res (.+)$"))
async def set_list_mode(bot, query):
    user_id = query.from_user.id
    result_mode = query.data.split()[1]
    if result_mode == "btnn":
        await change_search_settings(
            user_id, button_mode=True, link_mode=False, list_mode=False
        )
    if result_mode == "link":
        await change_search_settings(
            user_id, button_mode=False, link_mode=True, list_mode=False
        )
    if result_mode == "list":
        await change_search_settings(
            user_id, button_mode=False, link_mode=False, list_mode=True
        )
    if result_mode == "mode":
        await query.answer(text="Toggle Button/Link/List Mode", show_alert=False)
        return

    set_kb = await find_search_settings(user_id)

    await query.message.edit(
        text=SET_MSG,
        reply_markup=set_kb,
    )


async def find_search_settings(user_id):
    search_settings = await get_search_settings(user_id)

    kb = [
        InlineKeyboardButton("[Precise Mode]:", callback_data="prec md"),
    ]

    on_kb = InlineKeyboardButton("❌ Disabled", callback_data="prec on")
    off_kb = InlineKeyboardButton("✅ Enabled", callback_data="prec off")

    if search_settings:
        precise_mode = search_settings.precise_mode
        if precise_mode:
            precise_mode = "Enabled"
            kb.append(off_kb)
        else:
            precise_mode = "Disabled"
            kb.append(on_kb)
    else:
        await change_search_settings(user_id)
        precise_mode = "Disabled"
        kb.append(on_kb)

    bkb = [
        InlineKeyboardButton("[Result Mode]:", callback_data="res mode"),
    ]

    btn_kb = InlineKeyboardButton("📃 List", callback_data="res btnn")
    link_kb = InlineKeyboardButton("🔳 Button", callback_data="res link")
    list_kb = InlineKeyboardButton("🔗 HyperLink", callback_data="res list")

    if search_settings:
        button_mode = search_settings.button_mode
        link_mode = search_settings.link_mode
        list_mode = search_settings.list_mode
        if button_mode:
            bkb.append(link_kb)
        elif link_mode:
            bkb.append(list_kb)
        elif list_mode:
            bkb.append(btn_kb)
        else:
            await change_search_settings(user_id, link_mode=True)
            bkb.append(list_kb)
    else:
        await change_search_settings(user_id, link_mode=True)
        bkb.append(btn_kb)

    set_kb = InlineKeyboardMarkup([kb, bkb])

    return set_kb
