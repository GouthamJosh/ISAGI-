#CREDITS TO @CyberTGX

import os
import re
import logging
import logging.config

# --- Setup Logging Early ---
# Make sure the logger exists before any logging call
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

# Optional: use config.ini if available
if os.path.exists("config.ini"):
    try:
        logging.config.fileConfig(fname="config.ini", disable_existing_loggers=False)
    except Exception as e:
        LOGGER.warning(f"Could not load logging config.ini: {e}")

# --- Regex Pattern ---
id_pattern = re.compile(r"^.\d+$")

# --- Environment Variables ---
APP_ID = os.environ.get("APP_ID", "11824466")
API_HASH = os.environ.get("API_HASH", "5afd3ea9d0018ed654ae39a87aee62c7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7975397394:AAEt0CkLwjUMAfmCJZ1Vre7zFz5vFreKTmU")
DB_URL = os.environ.get("DB_URL", "mongodb+srv://vj200812:vj200812@cluster0.btt0vy5.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://vj200812:vj200812@cluster0.btt0vy5.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.environ.get('DB_NAME', "CyberTG")

try:
    OWNER_ID = int(os.environ.get("OWNER_ID", "5130458445"))
except ValueError:
    OWNER_ID = 0
    LOGGER.warning("OWNER_ID environment variable is not a valid integer.")

ADMINS = [
    int(user) if id_pattern.search(user) else user
    for user in os.environ.get("ADMINS", "5483128891").split()
] + [OWNER_ID]

DB_CHANNELS = [
    int(ch) if id_pattern.search(ch) else ch
    for ch in os.environ.get("DB_CHANNELS", "").split()
]

# --- Import constants safely ---
try:
    import const
except Exception:
    import sample_const as const

START_MSG = const.START_MSG
START_KB = const.START_KB
HELP_MSG = const.HELP_MSG
HELP_KB = const.HELP_KB

# Adjust Pyrogram log level
logging.getLogger("pyrogram").setLevel(logging.WARNING)
