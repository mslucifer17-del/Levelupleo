import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('8409424851:AAHkLsnj1ZdwKehAEDmT8swYHTTRAu2BB1Y')  # Your LevelupLeobot token
BOT_USERNAME = '@@LevelUpLeobot'

# Database Configuration (PostgreSQL for production)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://db_03_10_2025_user:bAEs2tDmzNqOiEamRj1W27t1qOApw1pY@dpg-d3fnov15pdvs73bfo99g-a/db_03_10_2025')

# Gemini API Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Group Configuration
MAIN_GROUP_ID = os.getenv('-1002989717704')  # ThePromotionHub group ID
VIP_GROUP_ID = os.getenv('VIP_GROUP_ID')  # VIP Lounge group ID

# Bot Settings
XP_COOLDOWN_SECONDS = 60  # Cooldown between XP gains
SPOTLIGHT_HOUR = 12  # Hour of day to announce spotlight (24-hour format)

# Economy Settings
DAILY_BONUS_COINS = 100
LEVEL_UP_COIN_BONUS = 50
