from pyrogram import Client, filters
from mfinder import DB_CHANNELS, LOGGER
from mfinder.db.files_sql import save_file
from mfinder.utils.helpers import edit_caption

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(DB_CHANNELS) & media_filter)
async def live_index(bot, message):
    try:
        media = None
        file_type = None

        # Detect media type safely
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
            return

        # Build clean file data (NO object mutation)
        file_data = {
            "file_id": media.file_id,
            "file_unique_id": media.file_unique_id,
            "file_name": edit_caption(media.file_name),
            "file_size": media.file_size,
            "mime_type": media.mime_type,
            "file_type": file_type,
            "caption": edit_caption(media.file_name),
        }

        await save_file(file_data)

    except Exception as e:
        LOGGER.warning(f"Live index error: {e}")
