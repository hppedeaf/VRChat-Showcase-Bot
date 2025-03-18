"""
Configuration settings for the VRChat World Showcase Bot.
"""
import os
import logging
from pathlib import Path
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

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
WELCOME_IMAGE_URL = "https://cdn.discordapp.com/avatars/1156538533876613121/e679e2cbdb24804661804a48c86f3e1e.png"