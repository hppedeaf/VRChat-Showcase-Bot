"""
Configuration settings for the VRChat World Showcase Bot.
"""
import os
import logging
from pathlib import Path
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

# VRChat API credentials
AUTH = os.getenv("VRCHAT_AUTH")
API_KEY = os.getenv("VRCHAT_API_KEY")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Using PostgreSQL on Railway
    DATABASE_FILE = DATABASE_URL
else:
    # Local SQLite fallback
    DATABASE_PATH = Path("database") / "vrchat_worlds.db"
    DATABASE_FILE = str(DATABASE_PATH)
    DATABASE_PATH.parent.mkdir(exist_ok=True)

# Logging
LOG_PATH = Path("logs")
LOG_PATH.mkdir(exist_ok=True)
LOG_FILE = LOG_PATH / "bot.log"

# Configure logging with Unicode support
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        # Use StreamHandler with a safe encoding for console output
        logging.StreamHandler(stream=sys.stdout)
    ]
)

# Workaround for Unicode issues in Windows console
if sys.platform == 'win32':
    # Replace the StreamHandler with one that handles encoding errors
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                '%Y-%m-%d %H:%M:%S'
            ))
            handler.setStream(sys.stdout)  # Use stdout which handles encoding better
            # Set an error handler that replaces problematic characters
            handler.formatter.encoding = 'utf-8'
            handler.formatter.errors = 'replace'

# Get logger
logger = logging.getLogger("vrchat_bot")

# Default tags for forum channels
DEFAULT_TAGS = {
    '🎮': 'Game',
    '📸': 'Photograph',
    '⛵': 'Adventure',
    '💥': 'Mind Blown',
    '🖼️': 'Heavy Render',
    '🎭': 'Roleplaying',
    '👻': 'Horror',
    '🛡': 'PVE',
    '⚔️': 'PVP',
    '🌴': 'Relaxing',
    '🧩': 'Puzzles',
    '😂': 'Funny',
    '🤪': 'Weird',
    '🔞': 'R-18',
    '🚪': 'Liminal'
}

# Forum settings
FORUM_LAYOUT_GALLERY = 2  # Gallery view (0=List, 1=Default, 2=Gallery)
DEFAULT_REACTION = "✅"    # Default reaction emoji
FORUM_NAME = "VRChat-World"      # Default name for forum channel 

# UI timeouts (in seconds)
BUTTON_TIMEOUT = None     # No timeout for persistent buttons
TAG_VIEW_TIMEOUT = 300    # 5 minutes for tag selection

# API settings
VRC_API_BASE_URL = "https://api.vrchat.cloud/api/1"
API_RETRY_ATTEMPTS = 3
API_TIMEOUT = 10
API_RETRY_DELAY = 2

# Welcome image URL
WELCOME_IMAGE_URL = "https://cdn.discordapp.com/avatars/1156538533876613121/8acb3d0ce2c328987ad86355e0d0b528.png?size=4096"