import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your LevelupLeobot token
BOT_USERNAME = '@LevelupLeobot'

# Database Configuration (PostgreSQL for production)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/levelupleo')

# Gemini API Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Group Configuration
MAIN_GROUP_ID = os.getenv('MAIN_GROUP_ID')  # ThePromotionHub group ID
VIP_GROUP_ID = os.getenv('VIP_GROUP_ID')  # VIP Lounge group ID

# Bot Settings
XP_COOLDOWN_SECONDS = 60  # Cooldown between XP gains
SPOTLIGHT_HOUR = 12  # Hour of day to announce spotlight (24-hour format)

# Economy Settings
DAILY_BONUS_COINS = 100
LEVEL_UP_COIN_BONUS = 50
