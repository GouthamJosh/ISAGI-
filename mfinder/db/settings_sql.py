#CREDITS TO @CyberTGX

import threading
from pymongo import MongoClient, errors
from mfinder import DB_URL, LOGGER 

DB_NAME = "mfinder_db"
ADMIN_COLLECTION_NAME = "admin_settings"
SETTINGS_COLLECTION_NAME = "settings"

CLIENT = None
ADMIN_COLLECTION = None
SETTINGS_COLLECTION = None

def start_mongo():
    """Initializes the MongoDB client and collections."""
    global CLIENT, ADMIN_COLLECTION, SETTINGS_COLLECTION
    try:
        CLIENT = MongoClient(DB_URL)
        DB = CLIENT[DB_NAME]
        
        ADMIN_COLLECTION = DB[ADMIN_COLLECTION_NAME]
        SETTINGS_COLLECTION = DB[SETTINGS_COLLECTION_NAME]
        
        print("MongoDB connection established and collections initialized.")
        
    except errors.ConnectionFailure as e:
        print(f"Error connecting to MongoDB: {e}")
        raise

start_mongo()

INSERTION_LOCK = threading.RLock()


def get_default_admin_settings() -> dict:
    """Returns the default structure for the AdminSettings document."""
    return {
        "setting_name": "default",
        "auto_delete": 0,
        "custom_caption": None,
        "fsub_channel": None,
        "channel_link": None,
        "caption_uname": None,
        "repair_mode": False
    }

def get_default_user_settings(user_id: int) -> dict:
    """Returns the default structure for a new user Settings document."""
    return {
        "user_id": user_id,
        "precise_mode": None, 
        "button_mode": None,
        "link_mode": None,
        "list_mode": None
    }



async def get_search_settings(user_id: int) -> dict | None:
    """Retrieves a user's search settings."""
    try:
        with INSERTION_LOCK:
            settings = SETTINGS_COLLECTION.find_one({"user_id": user_id})
            return settings
    except Exception as e:
        LOGGER.warning("Error getting search settings: %s ", str(e))
        return None


async def change_search_settings(user_id: int, precise_mode: bool = None, button_mode: bool = None, link_mode: bool = None, list_mode: bool = None) -> bool | None:
    """Updates a user's search settings, creating the document if it doesn't exist."""
    try:
        with INSERTION_LOCK:
            update_fields = {}
            if precise_mode is not None:
                update_fields["precise_mode"] = precise_mode
            if button_mode is not None:
                update_fields["button_mode"] = button_mode
            if link_mode is not None:
                update_fields["link_mode"] = link_mode
            if list_mode is not None:
                update_fields["list_mode"] = list_mode

            result = SETTINGS_COLLECTION.update_one(
                {"user_id": user_id},
                {"$set": update_fields, "$setOnInsert": {"user_id": user_id}},
                upsert=True
            )
            return result.acknowledged
            
    except Exception as e:
        LOGGER.warning("Error changing search settings: %s ", str(e))
        return None 


def _update_admin_setting(field_name: str, value):
    """Handles the upsert logic for a single admin setting field."""
    with INSERTION_LOCK:
        update_doc = {"$set": {field_name: value}}
        
        default_insert = get_default_admin_settings()
        default_insert.pop(field_name, None)
        update_doc["$setOnInsert"] = default_insert

        ADMIN_COLLECTION.update_one(
            {"setting_name": "default"},
            update_doc,
            upsert=True
        )


async def set_repair_mode(repair_mode: bool):
    try:
        _update_admin_setting("repair_mode", repair_mode)
    except Exception as e:
        LOGGER.warning("Error setting repair mode: %s ", str(e))


async def set_auto_delete(dur: float):
    try:
        _update_admin_setting("auto_delete", dur)
    except Exception as e:
        LOGGER.warning("Error setting auto delete: %s ", str(e))


async def get_admin_settings() -> dict | None:
    """Retrieves admin settings, creating the default document if not found."""
    try:
        with INSERTION_LOCK:
            admin_setting = ADMIN_COLLECTION.find_one({"setting_name": "default"})
            
            if not admin_setting:
                ADMIN_COLLECTION.insert_one(get_default_admin_settings())
                admin_setting = ADMIN_COLLECTION.find_one({"setting_name": "default"}) 
            
            return admin_setting
            
    except Exception as e:
        LOGGER.warning("Error getting admin settings: %s", str(e))
        return None


async def set_custom_caption(caption: str):
    try:
        _update_admin_setting("custom_caption", caption)
    except Exception as e:
        LOGGER.warning("Error setting custom caption: %s ", str(e))


async def set_force_sub(channel: float): 
    try:
        _update_admin_setting("fsub_channel", channel)
    except Exception as e:
        LOGGER.warning("Error setting Force Sub channel: %s ", str(e))


async def set_channel_link(link: str):
    try:
        _update_admin_setting("channel_link", link)
    except Exception as e:
        LOGGER.warning("Error adding Force Sub channel link: %s ", str(e))

# ✅ Corrected get_channel() and get_link() functions

async def get_channel() -> int | bool:
    """Retrieve the Force Sub (update channel) ID as an integer."""
    try:
        channel_doc = ADMIN_COLLECTION.find_one(
            {"setting_name": "default"},
            {"fsub_channel": 1, "_id": 0}
        )

        if channel_doc and channel_doc.get("fsub_channel") is not None:
            try:
                # Ensure it's an integer (not float/string)
                return int(channel_doc["fsub_channel"])
            except (ValueError, TypeError):
                LOGGER.warning(
                    f"Invalid channel ID format: {channel_doc.get('fsub_channel')}"
                )
                return False
        return False

    except Exception as e:
        LOGGER.warning("Error getting channel: %s", str(e))
        return False


async def get_link() -> str | bool:
    """Retrieve the Force Sub channel invite link."""
    try:
        link_doc = ADMIN_COLLECTION.find_one(
            {"setting_name": "default"},
            {"channel_link": 1, "_id": 0}
        )

        if link_doc and link_doc.get("channel_link") is not None:
            link = str(link_doc["channel_link"]).strip()
            if link.startswith("https://t.me/"):
                return link
            else:
                LOGGER.warning(f"Invalid link format: {link}")
                return False
        return False

    except Exception as e:
        LOGGER.warning("Error getting link: %s", str(e))
        return False

async def set_username(username: str):
    try:
        _update_admin_setting("caption_uname", username)
    except Exception as e:
        LOGGER.warning("Error adding username: %s ", str(e))
