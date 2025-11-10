#CREDITS TO @im_goutham_josh

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
from mfinder.db.settings_sql import (
    get_search_settings,
    get_admin_settings,
    get_link,
    get_channel,
)
from mfinder.db.ban_sql import is_banned
from mfinder.db.filters_sql import is_filter
from mfinder import LOGGER

@Client.on_message(filters.group | filters.private & filters.text & filters.incoming)
async def give_filter(bot, message):
    await filter_(bot, message)

@Client.on_message(
    ~filters.regex(r"^\/") & filters.text & filters.private & filters.incoming
)
async def filter_(bot, message):
    user_id = message.from_user.id

    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    if await is_banned(user_id):
        await message.reply_text("You are banned. You can't use this bot.", quote=True)
        return

    # Force sub check only in PM
    if message.chat.type == "private":
        force_sub = await get_channel()
        if force_sub:
            try:
                user = await bot.get_chat_member(int(force_sub), user_id)
                if user.status == ChatMemberStatus.BANNED:
                    await message.reply_text("Sorry, you are Banned to use me.", quote=True)
                    return
            except UserNotParticipant:
                link = await get_link()
                await message.reply_text(
                    text="**Please join my Update Channel to use this Bot!**",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🤖 Join Channel", url=link)]]
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    quote=True,
                )
                return
            except Exception as e:
                LOGGER.warning(e)
                await message.reply_text(
                    text="Something went wrong, please contact my support group",
                    quote=True,
                )
                return

    admin_settings = await get_admin_settings()
    if admin_settings:
        if admin_settings.get('repair_mode'):
            return

    fltr = await is_filter(message.text)
    if fltr:
        await message.reply_text(
            text=fltr.message,
            quote=True,
        )
        return

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
            # Delete after 10 minutes (600 seconds)
            asyncio.create_task(delete_after(reply, message, 600))
        else:
            reply = await message.reply_text(
                text="No results found.\nOr retry with the correct spelling 🤐",
                quote=True,
            )
            # Delete after 30 seconds
            asyncio.create_task(delete_after(reply, message, 30))

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

async def get_result(search, page_no, user_id, username):
    search_settings = await get_search_settings(user_id)
    
    if search_settings:
        if search_settings.get('precise_mode'):
            files, count = await get_precise_filter_results(query=search, page=page_no)
            precise_search = "Enabled"
        else:
            files, count = await get_filter_results(query=search, page=page_no)
            precise_search = "Disabled"
    else:
        files, count = await get_filter_results(query=search, page=page_no)
        precise_search = "Disabled"

    # Force button mode only
    button_mode = "ON"
    link_mode = "OFF"
    search_md = "Button"

    if files:
        btn = []
        index = (page_no - 1) * 10
        crnt_pg = index // 10 + 1
        tot_pg = (count + 10 - 1) // 10
        result = f"**Search Query:** `{search}`\n**Total Results:** `{count}`\n**Page:** `{crnt_pg}/{tot_pg}`\n**Precise Search: **`{precise_search}`\n**Result Mode:** `{search_md}`\n"
        page = page_no
        for file in files:
            file_id = file.file_id
            filename = f"[{get_size(file.file_size)}]{file.file_name}"
            btn_kb = InlineKeyboardButton(
                text=f"{filename}", url=f"https://t.me/{username}?start={file_id}"
            )
            btn.append([btn_kb])

        nxt_kb = InlineKeyboardButton(
            text="Next >>",
            callback_data=f"nxt_pg {user_id} {page + 1} {search}",
        )
        prev_kb = InlineKeyboardButton(
            text="<< Previous",
            callback_data=f"prev_pg {user_id} {page - 1} {search}",
        )

        kb = []
        if crnt_pg == 1 and tot_pg > 1:
            kb = [nxt_kb]
        elif crnt_pg > 1 and crnt_pg < tot_pg:
            kb = [prev_kb, nxt_kb]
        elif tot_pg > 1:
            kb = [prev_kb]

        if kb:
            btn.append(kb)

        result = (
            result
            + "\n\n"
            + "🔻 __Tap on below corresponding file to download.__ 🔻"
        )

        return result, btn

    return None, None

async def send_file(bot, chat_id, file_id):
    filedetails = await get_file_details(file_id)
    admin_settings = await get_admin_settings()
    for files in filedetails:
        f_caption = files.caption
        if admin_settings.get('custom_caption'):
            f_caption = admin_settings.get('custom_caption')
        elif f_caption is None:
            f_caption = f"{files.file_name}"

        f_caption = "`" + f_caption + "`"

        if admin_settings.get('caption_uname'):
            f_caption = f_caption + "\n" + admin_settings.get('caption_uname')

        msg = await bot.send_cached_media(
            chat_id=chat_id,
            file_id=file_id,
            caption=f_caption,
            parse_mode=ParseMode.MARKDOWN,
        )

        if admin_settings.get('auto_delete'):
            delay_dur = admin_settings.get('auto_delete')
            delay = delay_dur / 60 if delay_dur > 60 else delay_dur
            delay = round(delay, 2)
            minsec = str(delay) + " mins" if delay_dur > 60 else str(delay) + " secs"
            disc = await bot.send_message(
                chat_id,
                f"Please save the file to your saved messages, it will be deleted in {minsec}",
            )
            await asyncio.sleep(delay_dur)
            await disc.delete()
            await msg.delete()
            await bot.send_message(chat_id, "File has been deleted")

@Client.on_callback_query(filters.regex(r"^file (.+)$"))
async def get_files(bot, query):
    user_id = query.from_user.id
    file_id = query.data.split()[1]
    await query.answer("Sending file...", cache_time=60)
    await send_file(bot, user_id, file_id)

@Client.on_message(filters.private & filters.command("start"))
async def start(bot, message):
    if len(message.command) > 1:
        file_id = message.command[1]
        user_id = message.from_user.id

        # Check force sub in PM before sending file
        force_sub = await get_channel()
        if force_sub:
            try:
                user = await bot.get_chat_member(int(force_sub), user_id)
                if user.status == ChatMemberStatus.BANNED:
                    await message.reply_text("Sorry, you are Banned to use me.", quote=True)
                    return
            except UserNotParticipant:
                link = await get_link()
                await message.reply_text(
                    text="**Please join my Update Channel to use this Bot!**",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🤖 Join Channel", url=link)]]
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    quote=True,
                )
                return
            except Exception as e:
                LOGGER.warning(e)
                await message.reply_text(
                    text="Something went wrong, please contact my support group",
                    quote=True,
                )
                return

        await send_file(bot, user_id, file_id)
    else:
        await message.reply_text("Welcome! Send me a search query.")

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"

async def delete_after(bot_msg, user_msg, delay):
    await asyncio.sleep(delay)
    try:
        await bot_msg.delete()
        await user_msg.delete()
    except Exception as e:
        LOGGER.warning(f"Failed to delete messages: {e}")
