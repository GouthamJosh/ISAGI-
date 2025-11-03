#CREDITS TO @CyberTGX

import os
import re
from mfinder import ADMINS, MONGO_URI 
from pymongo import MongoClient 
from pymongo.errors import ConnectionFailure

def is_admin(user_id):
    """Checks if a user_id is in the list of bot admins."""
    return user_id in ADMINS

def humanbytes(B):
    """Return the given bytes as a human-friendly KB, MB, GB, or TB string"""
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2)  
    GB = float(KB ** 3)  
    TB = float(KB ** 4)  

    if B < KB:
        return f'{B} {"Bytes" if 0 == B or B > 1 else "Byte"}'
    elif KB <= B < MB:
        return f'{B/KB:.2f} KB'
    elif MB <= B < GB:
        return f'{B/MB:.2f} MB'
    elif GB <= B < TB:
        return f'{B/GB:.2f} GB'
    elif TB <= B:
        return f'{B/TB:.2f} TB'


def get_db_size() -> float:
    """
    Retrieves the total size of the MongoDB database in Megabytes (MB).
    This includes data size and index size.
    """
    try:
        client = MongoClient(MONGO_URI)
        db_name = client.get_default_database().name
        db = client[db_name]
        stats = db.command('dbStats')
        total_size_bytes = stats.get('storageSize', 0) 
        database_size_mb = total_size_bytes / (1024.0 * 1024.0)
        client.close()
        return round(database_size_mb, 2)
        
    except ConnectionFailure as e:
        print(f"Error connecting to MongoDB: {e}")
        return 0.0
    except Exception as e:
        print(f"Error retrieving MongoDB size: {e}")
        return 0.0



