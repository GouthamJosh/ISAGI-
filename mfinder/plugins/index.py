# CREDITS TO @im_goutham_josh

import asyncio
import time
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from mfinder import ADMINS, LOGGER
from mfinder.db.files_sql import save_file, delete_file
from mfinder.utils.helpers import edit_caption

lock = asyncio.Lock()
media_filter = filters.document | filters.video | filters.audio
SKIP = 0  # Global skip variable


# --------------------------------------------------------------------------------
#  Handle forward message and ask for indexing confirmation
# --------------------------------------------------------------------------------
@Client.on_message(filters.private & filters.user(ADMINS) & media_filter)
async def index_files(bot, message):
    user_id = message.from_user.id
    if lock.locked():
        return await message.reply("Wait until previous process complete.")

    try:
        last_msg_id = message.forward_from_message_id

        if message.forward_from_chat.username:
            chat_id = message.forward_from_chat.username
        else:
            chat_id = message.forward_from_chat.id

        await bot.get_messages(chat_id, last_msg_id)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Proceed", callback_data=f"index {chat_id} {last_msg_id}")],
            [InlineKeyboardButton("Cancel", callback_data="can-index")],
        ])

        await bot.send_message(
            user_id,
            "Please confirm if you want to start indexing",
            reply_markup=kb,
        )

    except Exception as e:
        await message.reply_text(
            "Unable to start indexing.\n"
            "Either the channel is private and bot is not admin OR message was forwarded as copy.\n"
            f"Error: <code>{e}</code>"
        )


# --------------------------------------------------------------------------------
#  MAIN INDEXING PROCESS — FIXED (NO CONSTANT DOCUMENT BUG)
# --------------------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^index .* \d+$"))
async def index(bot, query):
    user_id = query.from_user.id

    parts = query.data.split()
    chat_id_str = parts[1]
    last_msg_id = int(parts[2])

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        chat_id = chat_id_str

    await query.message.delete()
    msg = await bot.send_message(user_id, "Processing Index...⏳")

    BATCH_SIZE = 50
    total_files = 0
    start_time = time.time()

    async with lock:
        try:
            total = last_msg_id + 1
            current = SKIP + 2

            if current >= total:
                return await msg.edit("Skip value is too high, no messages to index.")

            while current < total:
                batch_ids = list(range(current, min(current + BATCH_SIZE, total)))

                try:
                    messages = await bot.get_messages(chat_id, batch_ids, replies=0)
                except FloodWait as e:
                    LOGGER.warning(f"FloodWait: sleeping for {e.value}")
                    await asyncio.sleep(e.value)
                    continue
                except Exception as e:
                    LOGGER.warning(f"Fetch error: {e}")
                    current += BATCH_SIZE
                    continue

                save_tasks = []

                for message in messages:
                    if not message:
                        continue

                    media = None
                    file_type = None

                    if message.document:
                        media = message.document
                        file_type = "document"
                    elif message.video:
                        media = message.video
                        file_type = "video"
                    elif message.audio:
                        media = message.audio
                        file_type = "audio"

                    if not media:
                        continue

                    file_data = {
                        "file_id": media.file_id,
                        "file_unique_id": media.file_unique_id,
                        "file_name": edit_caption(media.file_name),
                        "file_size": media.file_size,
                        "mime_type": media.mime_type,
                        "file_type": file_type,
                        "caption": edit_caption(media.file_name),
                    }

                    save_tasks.append(save_file(file_data))

                if save_tasks:
                    results = await asyncio.gather(*save_tasks, return_exceptions=True)
                    for r in results:
                        if not isinstance(r, Exception):
                            total_files += 1

                current += BATCH_SIZE

                elapsed = time.time() - start_time
                speed = total_files / elapsed if elapsed > 0 else 0
                percent = (current / total) * 100

                bar_filled = int(percent // 5)
                bar = "█" * bar_filled + "░" * (20 - bar_filled)

                remaining = total - current
                eta_seconds = remaining / (speed * BATCH_SIZE) if speed > 0 else 0
                eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))

                try:
                    await msg.edit(
                        f"📁 **Indexing in progress...**\n\n"
                        f"**Progress:** `{bar}` {percent:.2f}%\n"
                        f"📦 Messages scanned: `{current}/{total}`\n"
                        f"✅ Files saved: `{total_files}`\n"
                        f"⚡ Speed: `{speed:.2f} files/sec`\n"
                        f"⏳ ETA: `{eta_str}`"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value)

        except Exception as e:
            LOGGER.exception(e)
            await msg.edit(f"Error: {e}")
        else:
            await msg.edit(
                f"🎉 **Index Completed!**\n\n"
                f"Total files saved: **{total_files}**"
            )


# --------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------
@Client.on_message(filters.command(["index"]) & filters.user(ADMINS))
async def index_comm(bot, update):
    await update.reply(
        "Forward the **last message** of the channel you want to index.\n"
        "Bot must be admin of the channel if private."
    )


@Client.on_message(filters.command(["setskip"]) & filters.user(ADMINS))
async def set_skip(bot, message):
    global SKIP
    try:
        x = int(message.text.split()[1])
        if x < 0:
            return await message.reply("Skip value must be non-negative.")
        SKIP = x
        await message.reply(f"Skip set to {SKIP}. Index starts from message ID {SKIP + 2}.")
    except:
        await message.reply("Usage: /setskip <number>\nExample: /setskip 100")


@Client.on_message(filters.command(["delete"]) & filters.user(ADMINS))
async def delete_files(bot, message):
    if not message.reply_to_message:
        return await message.reply("Reply to a file to delete.")

    msg = message.reply_to_message
    try:
        for file_type in ("document", "video", "audio"):
            media = getattr(msg, file_type, None)
            if media:
                status = await delete_file(media)
                if status == "Not Found":
                    await message.reply(f"`{media.file_name}` not found.")
                elif status is True:
                    await message.reply(f"`{media.file_name}` deleted.")
                else:
                    await message.reply(f"Error while deleting `{media.file_name}`.")
    except Exception as e:
        LOGGER.warning(e)
        await message.reply("An error occurred while deleting.")


@Client.on_callback_query(filters.regex(r"^can-index$"))
async def cancel_index(bot, query):
    await query.message.delete()
