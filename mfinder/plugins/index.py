#CREDITS TO @im_goutham_josh

import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from mfinder import ADMINS, LOGGER
from mfinder.db.files_sql import save_file, delete_file
from mfinder.utils.helpers import edit_caption

lock = asyncio.Lock()
media_filter = filters.document | filters.video | filters.audio
SKIP = 0  # Global skip variable, default 0

@Client.on_message(filters.private & filters.user(ADMINS) & media_filter)
async def index_files(bot, message):
    user_id = message.from_user.id
    if lock.locked():
        await message.reply("Wait until previous process complete.")
    else:
        try:
            last_msg_id = message.forward_from_message_id
            if message.forward_from_chat.username:
                chat_id = message.forward_from_chat.username
            else:
                chat_id = message.forward_from_chat.id
            await bot.get_messages(chat_id, last_msg_id)
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Proceed", callback_data=f"index {chat_id} {last_msg_id}"
                        )
                    ],
                    [InlineKeyboardButton("Cancel", callback_data="can-index")],
                ]
            )
            await bot.send_message(
                user_id,
                "Please confirm if you want to start indexing",
                reply_markup=kb,
            )
        except Exception as e:
            await message.reply_text(
                f"Unable to start indexing, either the channel is private and bot is not an admin in the forwarded chat, or you forwarded message as copy.\nError caused due to <code>{e}</code>"
            )

@Client.on_callback_query(filters.regex(r"^index .* \d+$"))
async def index(bot, query):
    user_id = query.from_user.id
    
    # Split and extract parts
    parts = query.data.split()
    chat_id_str = parts[1]
    last_msg_id = int(parts[2])

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        chat_id = chat_id_str 

    await query.message.delete()
    msg = await bot.send_message(user_id, "Processing Index...⏳")
    total_files = 0
    BATCH_SIZE = 50  # Adjustable batch size for fetching messages
    
    async with lock:
        try:
            total = last_msg_id + 1
            current = SKIP + 2  # Start from SKIP + 2 to skip messages
            if current >= total:
                await msg.edit("Skip value is too high, no messages to index.")
                return
            
            while current < total:
                batch_ids = list(range(current, min(current + BATCH_SIZE, total)))
                try:
                    messages = await bot.get_messages(chat_id=chat_id, message_ids=batch_ids, replies=0)
                except FloodWait as e:
                    LOGGER.warning("FloodWait while batch fetching, sleeping for: %s", e.value)
                    await asyncio.sleep(e.value)
                    continue  # Retry the batch
                except Exception as e:
                    LOGGER.warning("Error fetching batch: %s", str(e))
                    current += BATCH_SIZE  # Skip the problematic batch
                    continue
                
                # Process the batch: Collect save tasks for concurrency
                save_tasks = []
                for message in messages:
                    if message and any(getattr(message, file_type, None) for file_type in ("document", "video", "audio")):
                        # Early check: Only process if message has media
                        for file_type in ("document", "video", "audio"):
                            media = getattr(message, file_type, None)
                            if media:
                                file_name = media.file_name
                                file_name = edit_caption(file_name)
                                media.file_type = file_type
                                media.caption = file_name
                                save_tasks.append(save_file(media))  # Add to concurrent tasks
                
                # Execute saves concurrently
                if save_tasks:
                    results = await asyncio.gather(*save_tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, Exception):
                            LOGGER.warning("Error in concurrent save: %s", str(result))
                        else:
                            total_files += 1
                
                current += BATCH_SIZE
                
                # Update progress less frequently (every 500 files)
                if total_files % 50 == 0:
                    try:
                        await msg.edit(f"🔦Total messages fetched: {current}\n✅Total files saved: {total_files}")
                    except FloodWait as e:
                        LOGGER.warning("FloodWait on progress update, sleeping for: %s", e.value)
                        await asyncio.sleep(e.value)
            
        except Exception as e:
            LOGGER.exception(e)
            await msg.edit(f"Error: {e}")
        else:
            await msg.edit(f"Total **{total_files}** files saved to database!")

@Client.on_message(filters.command(["index"]) & filters.user(ADMINS))
async def index_comm(bot, update):
    await update.reply(
        "Now please forward the **last message** of the channel you want to index & follow the steps. Bot must be admin of the channel if the channel is private."
    )

@Client.on_message(filters.command(["setskip"]) & filters.user(ADMINS))
async def set_skip(bot, message):
    global SKIP
    try:
        skip_value = int(message.text.split()[1])
        if skip_value < 0:
            await message.reply("Skip value must be non-negative.")
            return
        SKIP = skip_value
        await message.reply(f"Skip set to {SKIP}. Indexing will start from message ID {SKIP + 2}.")
    except (IndexError, ValueError):
        await message.reply("Usage: /setskip <number>\nExample: /setskip 100")

@Client.on_message(filters.command(["delete"]) & filters.user(ADMINS))
async def delete_files(bot, message):
    if not message.reply_to_message:
        await message.reply("Please reply to a file to delete")
        return 
        
    org_msg = message.reply_to_message
    try:
        for file_type in ("document", "video", "audio"):
            media = getattr(org_msg, file_type, None)
            
            if media: 
                del_file = await delete_file(media)
                if del_file == "Not Found":
                    await message.reply(f"`{media.file_name}` not found in database")
                elif del_file is True:
                    await message.reply(f"`{media.file_name}` deleted from database")
                else:
                    await message.reply(
                        f"Error occurred while deleting `{media.file_name}`, please check logs for more info"
                    )
                
    except Exception as e:
        LOGGER.warning("Error occurred while deleting file: %s", str(e))

@Client.on_callback_query(filters.regex(r"^can-index$"))
async def cancel_index(bot, query):
    await query.message.delete()
