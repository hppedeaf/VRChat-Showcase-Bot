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

# Discord Application Settings
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/callback")

# Bot token
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

# Bot invite/OAuth URLs
BOT_PERMISSIONS = os.getenv("BOT_PERMISSIONS", "8")  # 8 is Administrator permission
BOT_INVITE_URL = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={BOT_PERMISSIONS}&scope=bot%20applications.commands"
OAUTH_LOGIN_URL = f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"

# VRChat API credentials
AUTH = os.getenv("VRCHAT_AUTH")
API_KEY = os.getenv("VRCHAT_API_KEY")

# Database
# PostgreSQL connection parameters
PG_HOST = os.environ.get('PGHOST') or os.environ.get('POSTGRES_HOST')
PG_PORT = os.environ.get('PGPORT') or os.environ.get('POSTGRES_PORT', '5432')
PG_USER = os.environ.get('PGUSER') or os.environ.get('POSTGRES_USER')
PG_PASSWORD = os.environ.get('PGPASSWORD') or os.environ.get('POSTGRES_PASSWORD')
PG_DATABASE = os.environ.get('PGDATABASE') or os.environ.get('POSTGRES_DB', 'postgres')

# Construct PostgreSQL URL for compatibility with existing code
if PG_HOST and PG_USER and PG_PASSWORD:
    # Check if we're running locally with Railway settings
    if not os.environ.get('RAILWAY_ENVIRONMENT') and "railway" in (PG_HOST or ""):
        DATABASE_URL = None  # Disable PostgreSQL when running locally with Railway settings
    else:
        DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
else:
    DATABASE_URL = None

# Set PG_AVAILABLE flag based on initial environment check
# This flag will be updated at runtime based on actual connection attempts
PG_AVAILABLE = DATABASE_URL is not None

# PostgreSQL correction setting - set to False to disable automatic migration/correction
ATTEMPT_PG_CORRECTION = os.getenv("ATTEMPT_PG_CORRECTION", "TRUE").upper() == "TRUE"

# Setup SQLite database as fallback
DATABASE_PATH = Path("database") / "vrchat_worlds.db"
DATABASE_FILE = str(DATABASE_PATH)
DATABASE_PATH.parent.mkdir(exist_ok=True)

# Function to check if PostgreSQL connection parameters are available
def is_postgres_available():
    """Check if PostgreSQL connection variables are available."""
    return bool(PG_HOST and PG_USER and PG_PASSWORD)

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
TAG_VIEW_TIMEOUT = 120    # 2 minutes for tag selection

# API settings
VRC_API_BASE_URL = "https://api.vrchat.cloud/api/1"
API_RETRY_ATTEMPTS = 3
API_TIMEOUT = 10
API_RETRY_DELAY = 2

# Welcome image URL
WELCOME_IMAGE_URL = "https://cdn.discordapp.com/avatars/1156538533876613121/8acb3d0ce2c328987ad86355e0d0b528.png?size=4096"

# Web Dashboard Settings
DASHBOARD_TITLE = "VRChat Helper"
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

"""
VRChat API configuration settings.
These settings control how the bot interacts with the VRChat API.
"""

# VRChat API credentials
# The AUTH token will be loaded from vrchat_auth.json instead of requiring login
AUTH_FILE = "vrchat_auth.json"
AUTH_EXPIRY_DAYS = 14  # VRChat auth tokens typically last for 14-30 days

# VRChat API settings
VRC_API_BASE_URL = "https://api.vrchat.cloud/api/1"
VRC_API_MAX_RETRIES = 3
VRC_API_TIMEOUT = 10  # seconds
VRC_API_RETRY_DELAY = 2  # seconds

# Token check interval (to avoid excessive API calls)
VRC_TOKEN_CHECK_INTERVAL = 3600  # 1 hour in seconds

# Whether to automatically attempt login when token is invalid
# We'll set this to False to prevent unwanted login attempts
VRC_AUTO_LOGIN = True