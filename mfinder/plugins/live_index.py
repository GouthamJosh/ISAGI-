from pyrogram import Client, filters
from mfinder import DB_CHANNELS, LOGGER
from mfinder.db.files_sql import save_file
from mfinder.utils.helpers import edit_caption

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(DB_CHANNELS) & media_filter)
async def live_index(bot, message):
    try:
        # detect media type
        media = None
        file_type = None

        for f_type in ("document", "video", "audio"):
            obj = getattr(message, f_type, None)
            if obj is not None:
                media = obj
                file_type = f_type
                break

        if not media:
            return  # no valid media found

        # process file name
        file_name = edit_caption(media.file_name)

        media.file_type = file_type
        media.caption = file_name   # or use original caption if needed

        await save_file(media)

    except Exception as e:
        LOGGER.warning("Error occurred while saving file: %s", str(e))
