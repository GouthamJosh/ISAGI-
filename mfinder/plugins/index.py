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
SKIP = 0  # Global skip variable, default 0


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

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Proceed", callback_data=f"index {chat_id} {last_msg_id}")],
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
            "Unable to start indexing.\n"
            "Either the channel is private and bot is not admin OR message was forwarded as copy.\n"
            f"Error: <code>{e}</code>"
        )


# --------------------------------------------------------------------------------
#  MAIN INDEXING PROCESS — with ETA, SPEED, PROGRESS BAR
# --------------------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^index .* \d+$"))
async def index(bot, query):
    user_id = query.from_user.id

    # Extract chat_id and last_msg_id
    parts = query.data.split()
    chat_id_str = parts[1]
    last_msg_id = int(parts[2])

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        chat_id = chat_id_str

    # Remove confirmation message
    await query.message.delete()
    msg = await bot.send_message(user_id, "Processing Index...⏳")

    BATCH_SIZE = 50
    total_files = 0

    # For ETA / SPEED
    start_time = time.time()

    async with lock:
        try:
            total = last_msg_id + 1
            current = SKIP + 2

            if current >= total:
                return await msg.edit("Skip value is too high, no messages to index.")

            while current < total:

                # ---------------------------------------
                # Build batch id list
                # ---------------------------------------
                batch_ids = list(range(current, min(current + BATCH_SIZE, total)))

                try:
                    messages = await bot.get_messages(chat_id=chat_id, message_ids=batch_ids, replies=0)
                except FloodWait as e:
                    LOGGER.warning(f"FloodWait: sleeping for {e.value}")
                    await asyncio.sleep(e.value)
                    continue
                except Exception as e:
                    LOGGER.warning(f"Error fetching batch: {e}")
                    current += BATCH_SIZE
                    continue

                # ---------------------------------------
                # Prepare save tasks (for concurrency)
                # ---------------------------------------
                save_tasks = []
                for message in messages:
                    if not message:
                        continue

                    for file_type in ("document", "video", "audio"):
                        media = getattr(message, file_type, None)
                        if media:
                            file_name = edit_caption(media.file_name)
                            media.file_type = file_type
                            media.caption = file_name
                            save_tasks.append(save_file(media))
                            break

                # Save concurrently
                if save_tasks:
                    results = await asyncio.gather(*save_tasks, return_exceptions=True)
                    for r in results:
                        if not isinstance(r, Exception):
                            total_files += 1

                # Move to next batch
                current += BATCH_SIZE

                # ---------------------------------------
                # Progress Bar + ETA + Speed Calculation
                # ---------------------------------------
                elapsed = time.time() - start_time
                speed = total_files / elapsed if elapsed > 0 else 0

                # Percent
                percent = (current / total) * 100
                bar_filled = int(percent // 5)  # 20-segment bar
                bar = "█" * bar_filled + "░" * (20 - bar_filled)

                # ETA
                remaining = total - current
                eta_seconds = remaining / (speed * BATCH_SIZE) if speed > 0 else 0
                eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))

                # Update every 50 files
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
            return await msg.edit(f"Error: {e}")

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
