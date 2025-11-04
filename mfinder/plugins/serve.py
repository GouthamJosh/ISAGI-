#CREDITS TO @CyberTGX

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


# -------------------------------------------------------------
# 1. MAIN FILTER HANDLER (Works in Private and Groups)
# -------------------------------------------------------------
@Client.on_message(
    ~filters.regex(r"^\/") & filters.text & filters.incoming
)
async def filter_(bot, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_private = chat_id == user_id  # Check if it's a private chat

    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    # --- Initial Checks ---
    if await is_banned(user_id):
        await message.reply_text("You are banned. You can't use this bot.", quote=True)
        return

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
    if admin_settings and admin_settings.get('repair_mode'):
        return

    fltr = await is_filter(message.text)
    if fltr:
        await message.reply_text(
            text=fltr.message,
            quote=True,
        )
        return

    # --- File Search Logic ---
    if 2 < len(message.text) < 100:
        search = message.text
        page_no = 1
        me = bot.me
        username = me.username
        
        # Pass 'is_private' to determine button generation strategy
        result, btn = await get_result(search, page_no, user_id, username, is_private)

        if result:
            reply_markup = InlineKeyboardMarkup(btn) if btn else None
            await message.reply_text(
                f"{result}",
                reply_markup=reply_markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                quote=True,
            )
        else:
            await message.reply_text(
                text="No results found.\nOr retry with the correct spelling 🤐",
                quote=True,
            )

# -------------------------------------------------------------
# 2. PAGINATION HANDLER (Group and Private)
# -------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^(nxt_pg|prev_pg) \d+ \d+ .+$"))
async def pages(bot, query):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    is_private = chat_id == user_id
    
    org_user_id, page_no, search = query.data.split(maxsplit=3)[1:]
    org_user_id = int(org_user_id)
    page_no = int(page_no)
    me = bot.me
    username = me.username

    result, btn = await get_result(search, page_no, user_id, username, is_private)

    if result:
        try:
            reply_markup = InlineKeyboardMarkup(btn) if btn else None
            await query.message.edit(
                f"{result}",
                reply_markup=reply_markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except MessageNotModified:
            pass
    else:
        await query.message.reply_text(
            text="No results found.\nOr retry with the correct spelling 🤐",
            quote=True,
        )

# -------------------------------------------------------------
# 3. GROUP BUTTON HANDLER (New Handler for Group-to-DM link)
# -------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^start_dm_send (.+)$"))
async def start_send_file(bot, query):
    file_id = query.data.split()[1]
    me = bot.me
    
    # Create the deep link to send the file in DM
    start_link = f"https://t.me/{me.username}?start={file_id}"
    
    await query.answer("Tap the button to get the file in DM!", show_alert=True)
    
    # Send a new message to the user in the group with the "Open in DM" button
    await query.message.reply_text(
        text="**🔗 File Link**\n\nTo get the file, click the button below and tap **Start** in my private chat.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open in DM 📥", url=start_link)]]
        ),
        quote=True,
        parse_mode=ParseMode.MARKDOWN
    )

# -------------------------------------------------------------
# 4. FILE SEND HANDLER (Modified for DM-only delivery)
# -------------------------------------------------------------
@Client.on_message(filters.command("start") & filters.private, group=1)
async def start_handler_for_file(bot, message):
    if len(message.text.split()) > 1:
        # This is a deep link with a file_id, e.g., /start file_id_xyz
        file_id = message.text.split()[1]
        await get_files(bot, message, file_id)
        return
    # Add your regular /start command logic here if needed, 
    # otherwise, just return or send a welcome message.
    await message.reply_text("Hello! Send me a search query to find files.")


@Client.on_callback_query(filters.regex(r"^file (.+)$"))
async def get_files_callback(bot, query):
    file_id = query.data.split()[1]
    await get_files(bot, query, file_id)


async def get_files(bot, query_or_message, file_id):
    user_id = query_or_message.from_user.id
    
    # Only proceed if it's a private chat
    if isinstance(query_or_message, CallbackQuery):
        await query_or_message.answer("Sending file...", cache_time=60)
        cbq = True
        chat_id = query_or_message.message.chat.id
    elif isinstance(query_or_message, Message):
        cbq = False
        chat_id = query_or_message.chat.id
        
    if chat_id != user_id: # Guard against sending file in a non-private chat (shouldn't happen with the new logic, but safe)
        if cbq:
            await query_or_message.answer("Files can only be sent in private chat!", show_alert=True)
        else:
            await query_or_message.reply_text("Files can only be sent in private chat!")
        return
    
    filedetails = await get_file_details(file_id)
    admin_settings = await get_admin_settings()
    
    for files in filedetails:
        # ... (Rest of your existing file caption and media sending logic) ...
        f_caption = files.caption
        if admin_settings and admin_settings.get('custom_caption'):
            f_caption = admin_settings.get('custom_caption')
        elif f_caption is None:
            f_caption = f"{files.file_name}"

        f_caption = "`" + f_caption + "`"

        if admin_settings and admin_settings.get('caption_uname'):
            f_caption = f_caption + "\n" + admin_settings.get('caption_uname')

        # Send the file (This is guaranteed to be in a DM based on calling context)
        msg = await bot.send_cached_media(
                chat_id=user_id, # Always send to the user's ID
                file_id=file_id,
                caption=f_caption,
                parse_mode=ParseMode.MARKDOWN,
            )

        # ... (Rest of your auto_delete logic) ...
        if admin_settings and admin_settings.get('auto_delete'):
            delay_dur = admin_settings.get('auto_delete')
            delay = delay_dur / 60 if delay_dur > 60 else delay_dur
            delay = round(delay, 2)
            minsec = str(delay) + " mins" if delay_dur > 60 else str(delay) + " secs"
            disc = await bot.send_message(
                user_id,
                f"Please save the file to your saved messages, it will be deleted in {minsec}",
            )
            await asyncio.sleep(delay_dur)
            await disc.delete()
            await msg.delete()
            await bot.send_message(user_id, "File has been deleted")

# -------------------------------------------------------------
# 5. GET RESULT FUNCTION (Modified to handle Group vs. Private)
# -------------------------------------------------------------
async def get_result(search, page_no, user_id, username, is_private):
    # ... (Search settings retrieval remains the same) ...
    search_settings = await get_search_settings(user_id)
    
    if search_settings and search_settings.get('precise_mode'):
        files, count = await get_precise_filter_results(query=search, page=page_no)
        precise_search = "Enabled"
    else:
        files, count = await get_filter_results(query=search, page=page_no)
        precise_search = "Disabled"
        
    button_mode = search_settings.get('button_mode') if search_settings else False
    link_mode = search_settings.get('link_mode') if search_settings else False

    if button_mode and not link_mode:
        search_md = "Button"
    elif link_mode and not button_mode:
        search_md = "HyperLink"
    else:
        search_md = "List Button" # Default/Combined

    if files:
        btn = []
        index = (page_no - 1) * 10
        crnt_pg = index // 10 + 1
        tot_pg = (count + 10 - 1) // 10
        btn_count = 0
        
        result = f"**Search Query:** `{search}`\n**Total Results:** `{count}`\n**Page:** `{crnt_pg}/{tot_pg}`\n**Precise Search: **`{precise_search}`\n**Result Mode:** `{search_md}`\n"
        page = page_no
        
        # --- LOGIC DIFFERENCE FOR GROUP/PRIVATE ---
        for file in files:
            file_id = file.file_id
            
            if is_private: # Original logic for private chat (file buttons or links)
                if button_mode and not link_mode: # Button mode
                    filename = f"[{get_size(file.file_size)}]{file.file_name}"
                    btn_kb = InlineKeyboardButton(
                        text=f"{filename}", callback_data=f"file {file_id}"
                    )
                    btn.append([btn_kb])
                elif link_mode and not button_mode: # HyperLink mode (sends to DM)
                    index += 1
                    filename = f"**{index}.** [{file.file_name}](https://t.me/{username}/?start={file_id}) - `[{get_size(file.file_size)}]`"
                    result += "\n" + filename
                else: # List Button mode (sends to DM)
                    index += 1
                    btn_count += 1
                    filename = (
                        f"**{index}.** `{file.file_name}` - `[{get_size(file.file_size)}]`"
                    )
                    result += "\n" + filename
                    btn_kb = InlineKeyboardButton(
                        text=f"{index}", callback_data=f"file {file_id}"
                    )
                    if btn_count == 1 or btn_count == 6:
                        btn.append([btn_kb])
                    elif 6 > btn_count > 1:
                        btn[0].append(btn_kb)
                    else:
                        btn[1].append(btn_kb)
            
            else: # New logic for Group chat (sends 'Open in DM' button)
                index += 1
                btn_count += 1
                filename = (
                    f"**{index}.** `{file.file_name}` - `[{get_size(file.file_size)}]`"
                )
                result += "\n" + filename
                
                # Button will link to 'start_dm_send' which creates the final /start link
                btn_kb = InlineKeyboardButton(
                    text=f"📥 {index}", callback_data=f"start_dm_send {file_id}"
                )

                if btn_count == 1 or btn_count == 6:
                    btn.append([btn_kb])
                elif 6 > btn_count > 1:
                    btn[0].append(btn_kb)
                else:
                    btn[1].append(btn_kb)
        # --- END OF LOGIC DIFFERENCE ---

        # ... (Pagination button logic remains the same) ...
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

        # ... (Result message text footer remains the same) ...
        if is_private:
            if button_mode and not link_mode:
                result = (
                    result
                    + "\n\n"
                    + "🔻 __Tap on below corresponding file number to download.__ 🔻"
                )
            elif link_mode and not button_mode:
                result = result + "\n\n" + " __Tap on file name & then start to download.__"
        else:
             # Custom message for group chat mode
             result = result + "\n\n" + "⚠️ **Files must be downloaded in DM.** Tap on the file number buttons to get the link."

        return result, btn

    return None, None


# ... (get_size function remains the same) ...
def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"
