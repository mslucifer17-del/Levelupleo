# -*- coding: utf-8 -*-
# LevelUp Leo Bot - Fixed and Enhanced for Render Deployment

import os
import logging
import random
import asyncio
import time
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, 
    ChatMemberHandler, filters, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func, BigInteger, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# --- Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db')
GROUP_ID = int(os.environ.get('GROUP_ID', 0))
PORT = int(os.environ.get('PORT', 8443))

if not all([BOT_TOKEN, GEMINI_API_KEY, GROUP_ID]):
    logger.critical("CRITICAL ERROR: BOT_TOKEN, GEMINI_API_KEY, or GROUP_ID is missing!")
    exit()

# Database Setup (SQLAlchemy)
Base = declarative_base()

# Database connection with retry logic
def create_db_engine():
    max_retries = 5
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            engine = create_engine(
                DATABASE_URL, 
                pool_size=10, 
                max_overflow=20, 
                pool_timeout=30, 
                pool_recycle=1800,
                connect_args={'connect_timeout': 30} if DATABASE_URL.startswith('postgresql') else {}
            )
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established successfully")
            return engine
        except SQLAlchemyError as e:
            logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.critical("Max database connection retries exceeded. Exiting.")
                raise

engine = create_db_engine()
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255), nullable=False)
    
    level = Column(Integer, default=0)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0)
    hubcoins = Column(Integer, default=10) # Start with 10 coins
    reputation = Column(Integer, default=0)
    
    last_message_date = Column(DateTime)
    join_date = Column(DateTime, default=datetime.now)
    
    # Shop & Perks
    vip_member = Column(Boolean, default=False)
    custom_title = Column(String(50), default="")
    custom_title_expiry = Column(DateTime)
    spotlight_priority = Column(Boolean, default=False)
    
    # New fields for enhanced features
    daily_streak = Column(Integer, default=0)
    last_daily_date = Column(DateTime)
    achievements = Column(String(500), default="")  # Store as JSON string
    
    def get_display_name(self):
        title = f" [{self.custom_title}]" if self.custom_title else ""
        prestige_badge = '🌟' * self.prestige if self.prestige > 0 else ''
        return f"{self.first_name}{title}{prestige_badge}"

# Function to check and alter table if needed
def check_and_alter_table():
    try:
        with engine.connect() as conn:
            # Check if user_id column is INTEGER type
            result = conn.execute(text("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'user_id';
            """))
            row = result.fetchone()
            if row and row[0] == 'integer':
                logger.info("Changing user_id column from integer to bigint")
                conn.execute(text("ALTER TABLE users ALTER COLUMN user_id TYPE BIGINT;"))
                conn.commit()
                logger.info("Column type changed successfully")
    except Exception as e:
        logger.error(f"Error checking/altering table: {e}")

# Create tables and check column types
try:
    Base.metadata.create_all(engine)
    # Check if we need to alter the user_id column for PostgreSQL
    if DATABASE_URL.startswith('postgresql'):
        check_and_alter_table()
except Exception as e:
    logger.error(f"Error creating database tables: {e}")

# Gemini AI Initialization
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Gemini AI configured successfully")
except Exception as e:
    logger.error(f"Failed to configure Gemini AI: {e}")
    gemini_model = None

# Sticker IDs
LEVEL_STICKERS = {
    1: ["CAACAgEAAxkBAAECZohow8nXm9oFdxnWioDIioN6859S4wACpQIAAkb-8Ec467BfJxQ8djYE"],
    2: ["CAACAgEAAxkBAAECaP1oxRfMvKFVsuGdqgFtWL8LoqKjMQACBQMAAnNOIERFC6_h0W0SgDYE"],
    4: ["CAACAgEAAxkBAAECaQFoxRf1T3qdVXZN623-6KUJarP_hQACfQMAAj7OWETdjsszH42-rzYE"],
    10: ["CAACAgIAAxkBAAECaQVoxRgnf9Tl_egizv2IzRq-p4JDPgACWDEAAvTKMEpYpE1ML4rwgTYE"],
    15: ["CgACAgQAAxkBAAECaQdoxRidErmqz3qB1miEt6Bf38ty2QACVwMAAolPBFMwDn_gBXkQejYE"],
    20: ["CAACAgUAAxkBAAECaQ9oxRkWl7-xcGPLi-lwXgABsioAAbKwAAIzDgAC5j65V5cS4rkdBo1VNgQ"],
    30: ["CAACAgIAAxkBAAECaRVoxRnUU7Q1SqXKZmqOZWSuAAHeGBMAAuENAAIxDJhKsojdm6OziV42BA"],
    40: ["CAACAgIAAxkBAAECaRdoxRoGN8TzhAkHosNsA2gmOx5rAgACjwYAAtJaiAEE4A-WIoMiBTYE"],
    50: ["CAACAgIAAxkBAAECaRloxRosJz8PPM_sXS5tYWkrERl1hgACEQEAAiteUwtIyKiZ9C1kczYE"],
    60: ["CAACAgEAAxkBAAECaR1oxRqgy5loi2Bn9H73XIDtgxS5DgACWQoAAr-MkARSHfGoioZ2dDYE"],
    70: ["CAACAgIAAxkBAAECaR9oxRsy5ik6Lafehl768jrOYUAgxgACMAADWbv8Jb2cViz8YDqINgQ"],
    100: ["CgACAgQAAxkBAAECaSNoxRyHpjl-ewc5MSsrH1KN5fGleQACXQcAApuxnVCKrIelHCgSAzYE"]
}

# Random level-up messages with user mentions
LEVEL_UP_MESSAGES = [
    "🎉 Congrats {}! you've leveled up to {level}! 🎉",
    "🚀 Nice work {}! you just hit Level {level}! 🚀",
    "🔥 Way to go {}! Level {level} unlocked! 🔥",
    "🌟 Big win {}! you've reached Level {level}! 🌟",
    "💫 Impressive {}! Level {level} achieved! 💫",
    "🏆 Champion vibes {}! Level {level} conquered! 🏆",
    "🎊 Cheers {}! you're officially on Level {level}! 🎊",
    "⚡ Energy unmatched {}! Level {level} unlocked! ⚡",
    "👑 King/Queen move {}! you've claimed Level {level}! 👑",
    "💎 Brilliant {}! you're shining at Level {level}! 💎",
    "🌈 Amazing {}! Level {level} completed! 🌈",
    "🎯 Spot on {}! you nailed Level {level}! 🎯",
    "🚀 Fast climb {}! Level {level} unlocked! 🚀",
    "🏅 Gold star {}! you've achieved Level {level}! 🅰️",
    "✨ Sparkling success {}! Level {level} reached! ✨"
]

# Achievement System
ACHIEVEMENTS = {
    "first_message": {"name": "First Words", "description": "Send your first message", "reward": 50},
    "level_10": {"name": "Rising Star", "description": "Reach level 10", "reward": 100},
    "level_50": {"name": "Half Century", "description": "Reach level 50", "reward": 500},
    "level_100": {"name": "Centurion", "description": "Reach level 100", "reward": 1000},
    "vip": {"name": "Elite Member", "description": "Purchase VIP status", "reward": 200},
    "streak_7": {"name": "Consistent", "description": "7-day message streak", "reward": 150},
    "streak_30": {"name": "Dedicated", "description": "30-day message streak", "reward": 500},
}

# --- Auto-Delete Functionality ---
async def delete_message_after_delay(bot, chat_id, message_id, delay=60):
    """Delete a message after a specified delay"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Message {message_id} deleted after {delay} seconds")
    except BadRequest as e:
        if "Message to delete not found" in str(e):
            logger.warning(f"Message {message_id} already deleted")
        else:
            logger.error(f"Error deleting message {message_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting message {message_id}: {e}")

# --- Core Bot Logic ---

# 1. Helper Functions
def get_level_requirements(level: int) -> int:
    """Calculates total messages needed for a certain level using a progressive formula."""
    if level <= 10: return level * 10
    elif level <= 25: return 100 + (level - 10) * 25
    elif level <= 50: return 475 + (level - 25) * 50
    else: return 1725 + (level - 50) * 100

def get_or_create_user(session, user_data) -> User:
    """Gets a user from the DB or creates a new one."""
    try:
        db_user = session.query(User).filter(User.user_id == user_data.id).first()
        if not db_user:
            db_user = User(
                user_id=user_data.id,
                username=user_data.username,
                first_name=user_data.first_name or "User",
            )
            session.add(db_user)
            session.commit()
            logger.info(f"Created new user: {user_data.id}")
        return db_user
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error getting/creating user: {e}")
        # Try to get user again in case of race condition
        db_user = session.query(User).filter(User.user_id == user_data.id).first()
        if not db_user:
            raise e
        return db_user

async def generate_level_up_message(level: int, user_mention: str) -> str:
    """Generates a unique level-up message using Gemini AI or random messages."""
    # Use Gemini if available
    if gemini_model:
        prompt = f"Write a very short, cool, and motivating message in Hinglish for a user who just reached Level {level} in a Telegram group. Mention the level. Be creative and fun."
        try:
            response = await asyncio.to_thread(
                gemini_model.generate_content, 
                prompt, 
                safety_settings={'HARASSMENT':'block_none'}
            )
            return f"{user_mention} {response.text.strip()}"
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
    
    # Fallback to random messages if Gemini fails or is not available
    message_template = random.choice(LEVEL_UP_MESSAGES)
    return message_template.format(user_mention, level=level)

async def check_achievements(session, user, achievement_type):
    """Check and award achievements to users."""
    if not user.achievements:
        user.achievements = ""
    
    if achievement_type in user.achievements:
        return False
        
    achievement = ACHIEVEMENTS.get(achievement_type)
    if not achievement:
        return False
        
    user.achievements += f"{achievement_type},"
    user.hubcoins += achievement["reward"]
    session.commit()
    
    return achievement

# 2. Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='stats'),
         InlineKeyboardButton("🛒 Shop", callback_data='shop')],
        [InlineKeyboardButton("🌟 Premium", callback_data='premium'),
         InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(
        "Namaste! Main LevelUp Leo hoon. Group mein message karke apni level badhao!",
        reply_markup=reply_markup
    )
    asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📜 **LevelUp Leo Commands** 📜\n\n"
        "`/stats` - Apni level, coins aur progress dekho.\n"
        "`/coins` - Apne HubCoins ka balance dekho.\n"
        "`/shop` - Dekho ki tum HubCoins se kya khareed sakte ho.\n"
        "`/buy [item]` - Shop se kuch khareedo (e.g., `/buy title`)\n"
        "`/prestige` - Level 100 ke baad special badge ke liye level reset karo.\n"
        "`/daily` - Roz ka reward claim karo.\n"
        "Reply to a message with `/rep` to give reputation to a user."
    )
    msg = await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        req_for_next = get_level_requirements(db_user.level + 1)
        messages_for_next = max(0, req_for_next - db_user.messages_count)
        
        # Create a visual progress bar
        progress = (db_user.messages_count - get_level_requirements(db_user.level)) / (req_for_next - get_level_requirements(db_user.level)) * 100
        progress = max(0, min(100, progress))
        progress_bar = "[" + "█" * int(progress / 5) + "░" * (20 - int(progress / 5)) + "]"
        
        stats_text = (
            f"📊 **{db_user.get_display_name()}'s Stats** 📊\n\n"
            f"• **Level:** {db_user.level} (Prestige {db_user.prestige}🌟)\n"
            f"• **Progress to next level:** {progress:.1f}%\n{progress_bar}\n"
            f"• **Messages:** {db_user.messages_count}\n"
            f"• **HubCoins:** {db_user.hubcoins} 💰\n"
            f"• **Reputation:** {db_user.reputation} 👍\n"
            f"• **Daily Streak:** {db_user.daily_streak or 0} days 🔥\n"
            f"• **Next Level:** in {messages_for_next} messages.\n"
            f"• **VIP Status:** {'Yes 🎖️' if db_user.vip_member else 'No'}\n"
            f"• **Achievements:** {len(db_user.achievements.split(',')) if db_user.achievements else 0} 🏆"
        )
        msg = await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        msg = await update.message.reply_text("Kuch error aaya hai. Thodi der baad try karo.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    finally:
        session.close()

async def prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        if db_user.level < 100:
            msg = await update.message.reply_text("Prestige ke liye Level 100 tak pahunchna zaroori hai!")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
            return

        db_user.prestige += 1
        db_user.level = 1
        db_user.messages_count = 0
        db_user.hubcoins += 500 * db_user.prestige # More coins for higher prestige
        session.commit()

        user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
        prestige_badge = '🌟' * db_user.prestige
        msg = await update.message.reply_text(
            f"🎊 CONGRATULATIONS, {user_mention}! 🎊\n\n"
            f"Aapne Prestige {db_user.prestige} haasil kar liya hai! {prestige_badge}\n"
            f"Aapki level reset ho gayi hai, aur aapko {500 * db_user.prestige} HubCoins ka bonus mila hai. Keep rocking!"
        )
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in prestige command: {e}")
        msg = await update.message.reply_text("Kuch error aaya hai. Thodi der baad try karo.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    finally:
        session.close()

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        today = datetime.now().date()
        last_daily = db_user.last_daily_date.date() if db_user.last_daily_date else None
        
        if last_daily and last_daily == today:
            msg = await update.message.reply_text("Aap aaj ka daily reward already le chuke hain! Kal fir try karein.")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
            return
        
        # Calculate streak
        streak = db_user.daily_streak or 0
        if last_daily and (today - last_daily).days == 1:
            streak += 1
        else:
            streak = 1
        
        # Calculate reward based on streak
        base_reward = 50
        streak_bonus = min(100, streak * 5)  # Max 100 coin bonus
        total_reward = base_reward + streak_bonus
        
        # Update user
        db_user.daily_streak = streak
        db_user.last_daily_date = datetime.now()
        db_user.hubcoins += total_reward
        session.commit()
        
        msg = await update.message.reply_text(
            f"🎉 Daily Reward Claimed! 🎉\n"
            f"Aapko mile {total_reward} HubCoins!\n"
            f"Streak: {streak} days\n"
            f"Kal fir aaye aur zyada coins kamayein!"
        )
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        
        # Check for streak achievements
        if streak == 7:
            await check_achievements(session, db_user, 'streak_7')
        elif streak == 30:
            await check_achievements(session, db_user, 'streak_30')
            
    except Exception as e:
        logger.error(f"Error in daily command: {e}")
        msg = await update.message.reply_text("Kuch error aaya hai. Thodi der baad try karo.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    finally:
        session.close()

# 3. Message and Member Handlers
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        session = Session()
        try:
            get_or_create_user(session, member) # User ko DB mein add karein
            
            # Use username if available, otherwise first name
            user_mention = f"@{member.username}" if member.username else member.first_name
            
            # Gen-Z style welcome messages with different fonts and emojis
            welcome_messages = [
                f"✨ 𝗪𝗲𝗹𝗰𝗺 {user_mention}  ✨\n\n"
                f"🎯 𝗧𝗾𝗾 𝗳𝗼𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴 𝗧𝗵𝗲𝗣𝗿𝗼𝗺𝗼𝘁𝗶𝗼𝗻𝗛𝘂𝗯  🎯\n\n"
                f"🌟 𝗬𝗼𝘂𝗿 𝗷𝗼𝘂𝗿𝗻𝗲𝘆 𝗯𝗲𝗴𝗶𝗻𝘀 𝗮𝘁 𝗹𝗲𝘃𝗲𝗹 𝟬  🌟\n"
                f"💬 𝗗𝗿𝗼𝗽 𝗺𝗲𝘀𝘀𝗮𝗴𝗲𝘀, 𝗹𝗲𝘃𝗲𝗹 𝘂𝗽 & 𝗲𝗮𝗿𝗻 𝗿𝗲𝘄𝗮𝗿𝗱𝘀  💬",
                
                f"🔥 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 {user_mention}  🔥\n\n"
                f"🎊 𝗧𝗵𝗮𝗻𝗸𝘀 𝗳𝗼𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴 𝘁𝗵𝗲 𝗳𝗮𝗺  🎊\n\n"
                f"🚀 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗹𝗲𝘃𝗲𝗹: 𝟬  🚀\n"
                f"💎 𝗦𝘁𝗮𝗿𝘁 𝗰𝗵𝗮𝘁𝘁𝗶𝗻𝗴 𝘁𝗼 𝗹𝗲𝘃𝗲𝗹 𝘂𝗽  💎",
                
                f"💫 𝗪𝗲𝗹𝗰𝗺 {user_mention}  💫\n\n"
                f"🌸 𝗧𝗾𝗾 𝗳𝗼𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴 𝗼𝘂𝗿 𝗰𝗼𝗺𝗺𝘂𝗻𝗶𝘁𝘆  🌸\n\n"
                f"📈 𝗬𝗼𝘂'𝗿𝗲 𝗮𝘁 𝗹𝗲𝘃𝗲𝗹 𝟬 𝗻𝗼𝘄  📈\n"
                f"🎯 𝗦𝗲𝗻𝗱 𝗺𝗲𝘀𝘀𝗮𝗴𝗲𝘀 𝘁𝗼 𝗹𝗲𝘃𝗲𝗹 𝘂𝗽  🎯",
                
                f"🎉 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 {user_mention}  🎉\n\n"
                f"💖 𝗧𝗵𝗮𝗻𝗸𝘀 𝗳𝗼𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴 𝗧𝗵𝗲𝗣𝗿𝗼𝗺𝗼𝘁𝗶𝗼𝗻𝗛𝘂𝗯  💖\n\n"
                f"✨ 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴 𝗹𝗲𝘃𝗲𝗹: 𝟬  ✨\n"
                f"🔥 𝗖𝗵𝗮𝘁 𝘁𝗼 𝗶𝗻𝗰𝗿𝗲𝗮𝘀𝗲 𝘆𝗼𝘂𝗿 𝗹𝗲𝘃𝗲𝗹  🔥",
                
                f"🌟 𝗪𝗲𝗹𝗰𝗺 {user_mention}  🌟\n\n"
                f"🎁 𝗧𝗾𝗾 𝗳𝗼𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴 𝘁𝗵𝗲 𝗵𝘂𝗯  🎁\n\n"
                f"🚀 𝗬𝗼𝘂'𝗿𝗲 𝗮𝘁 𝗹𝗲𝘃𝗲𝗹 𝟬  🚀\n"
                f"💎 𝗦𝘁𝗮𝗿𝘁 𝗺𝗲𝘀𝘀𝗮𝗴𝗶𝗻𝗴 𝘁𝗼 𝗹𝗲𝘃𝗲𝗹 𝘂𝗽  💎"
            ]
            
            # Random emoji combinations to add at the end
            emoji_combinations = [
                "✨🔥💫🌟🎯",
                "🚀💎🎊🌸💖",
                "🎉🔥🌟💫✨",
                "💎🚀🎯💖🌸",
                "✨🎊🔥💎🌟"
            ]
            
            welcome_text = random.choice(welcome_messages) + "\n\n" + random.choice(emoji_combinations)
            msg = await update.message.reply_text(welcome_text)
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id, 120))  # Delete after 2 minutes

            # Har message ke baad 1 second ka intezar karein
            await asyncio.sleep(1) 

        except Exception as e:
            logger.error(f"Welcome message error for {member.id}: {e}")
        finally:
            session.close()
            
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or update.effective_chat.id != GROUP_ID:
        return # Process messages only from the main group

    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        # Update counts
        db_user.messages_count += 1
        db_user.last_message_date = datetime.now()
        db_user.hubcoins += random.randint(1, 3) # Earn 1-3 coins per message
        
        # Check for first message achievement
        if db_user.messages_count == 1:
            await check_achievements(session, db_user, 'first_message')
        
        # Level Up Check
        old_level = db_user.level
        new_level = 0
        while db_user.messages_count >= get_level_requirements(new_level + 1):
            new_level += 1
        
        if new_level > old_level:
            db_user.level = new_level
            db_user.hubcoins += new_level * 10 # Bonus coins on level up
            
            # Check for level achievements
            if new_level == 10:
                await check_achievements(session, db_user, 'level_10')
            elif new_level == 50:
                await check_achievements(session, db_user, 'level_50')
            elif new_level == 100:
                await check_achievements(session, db_user, 'level_100')
            
            # Create user mention
            user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
            
            # Send random level-up message
            level_up_text = await generate_level_up_message(new_level, user_mention)
            level_up_msg = await update.message.reply_text(level_up_text)
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, level_up_msg.message_id))
            
            # Send random sticker for this level
            if new_level in LEVEL_STICKERS and LEVEL_STICKERS[new_level]:
                sticker_msg = await update.message.reply_sticker(random.choice(LEVEL_STICKERS[new_level]))
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, sticker_msg.message_id))
            
            # Prestige Prompt at Level 100
            if new_level == 100:
                prestige_msg = await update.message.reply_text(f"🎉 {user_mention} Aap Level 100 par pahunch gaye hain! Special badge ke liye /prestige command ka istemal karein!")
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, prestige_msg.message_id))
        
        # Delete the original user message after 1 minute
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, update.message.message_id))
        
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error handling message: {e}")
    finally:
        session.close()

# 4. Economy and Advanced Features
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🎭 Custom Title (1000)", callback_data='shop_title')],
        [InlineKeyboardButton("🌟 Spotlight (2500)", callback_data='shop_spotlight')],
        [InlineKeyboardButton("👑 VIP Status (10000)", callback_data='shop_vip')],
        [InlineKeyboardButton("🎨 Name Color (1500)", callback_data='shop_color')],
        [InlineKeyboardButton("🚀 Daily Boost (500)", callback_data='shop_boost')],
        [InlineKeyboardButton("« Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    shop_text = (
        "🛒 **ThePromotionHub Shop** 🛒\n\n"
        "Apne HubCoins se yeh items khareedo:\n\n"
        "Har item ke liye button dabao details dekhne ke liye!"
    )
    
    msg = await update.message.reply_text(shop_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        msg = await update.message.reply_text("Kya khareedna hai? Example: `/buy title My Awesome Title`")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        return

    item = args[0].lower()
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        if item == "title":
            title_text = " ".join(args[1:])
            if not title_text:
                msg = await update.message.reply_text("Title likhna zaroori hai. Example: `/buy title The King`")
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
                return
            if db_user.hubcoins < 1000:
                msg = await update.message.reply_text(f"Iske liye 1000 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
                return
            
            db_user.hubcoins -= 1000
            db_user.custom_title = title_text[:20] # Max 20 chars
            db_user.custom_title_expiry = datetime.now() + timedelta(days=7)
            session.commit()
            user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
            msg = await update.message.reply_text(f"Badhai ho {user_mention}! Aapka naya title '{db_user.custom_title}' ek hafte ke liye set ho gaya hai.")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))

        elif item == "spotlight":
            if db_user.hubcoins < 2500:
                msg = await update.message.reply_text(f"Iske liye 2500 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
                return
            db_user.hubcoins -= 2500
            db_user.spotlight_priority = True
            session.commit()
            user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
            msg = await update.message.reply_text(f"Kharidari safal {user_mention}! Aapko agle spotlight mein priority di jayegi. 🌟")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
            
        elif item == "vip":
            if db_user.hubcoins < 10000:
                msg = await update.message.reply_text(f"Iske liye 10000 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
                return
            db_user.hubcoins -= 10000
            db_user.vip_member = True
            session.commit()
            
            # Check for VIP achievement
            await check_achievements(session, db_user, 'vip')
            
            user_mention = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
            msg = await update.message.reply_text(f"Welcome to the VIP club {user_mention}! 🎖️ Aapko ab special perks milenge.")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        
        else:
            msg = await update.message.reply_text("Aisa koi item shop mein nahi hai. /shop dekho.")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in buy command: {e}")
        msg = await update.message.reply_text("Kuch error aaya hai. Thodi der baad try karo.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    finally:
        session.close()

async def rep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("Yeh command kisi message ko reply karke istemal karein.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        return
        
    giver = update.effective_user
    receiver = update.message.reply_to_message.from_user
    
    if giver.id == receiver.id:
        msg = await update.message.reply_text("Aap khud ko reputation nahi de sakte!")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        return
        
    session = Session()
    try:
        db_receiver = get_or_create_user(session, receiver)
        db_receiver.reputation += 1
        session.commit()
        giver_mention = f"@{giver.username}" if giver.username else giver.first_name
        receiver_mention = f"@{receiver.username}" if receiver.username else receiver.first_name
        msg = await update.message.reply_to_message.reply_text(f"{receiver_mention} ki reputation {giver_mention} ne badhai! Current reputation: {db_receiver.reputation} 👍")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in rep command: {e}")
        msg = await update.message.reply_text("Kuch error aaya hai. Thodi der baad try karo.")
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
    finally:
        session.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        await stats_command_with_query(query, context)
    elif query.data == 'shop':
        await shop_command_with_query(query, context)
    elif query.data == 'help':
        await help_command_with_query(query, context)
    elif query.data == 'premium':
        await premium_command_with_query(query, context)
    elif query.data == 'main_menu':
        await start_command_with_query(query, context)

async def stats_command_with_query(query, context):
    session = Session()
    try:
        db_user = get_or_create_user(session, query.from_user)
        
        req_for_next = get_level_requirements(db_user.level + 1)
        messages_for_next = max(0, req_for_next - db_user.messages_count)
        
        # Create a visual progress bar
        progress = (db_user.messages_count - get_level_requirements(db_user.level)) / (req_for_next - get_level_requirements(db_user.level)) * 100
        progress = max(0, min(100, progress))
        progress_bar = "[" + "█" * int(progress / 5) + "░" * (20 - int(progress / 5)) + "]"
        
        stats_text = (
            f"📊 **{db_user.get_display_name()}'s Stats** 📊\n\n"
            f"• **Level:** {db_user.level} (Prestige {db_user.prestige}🌟)\n"
            f"• **Progress to next level:** {progress:.1f}%\n{progress_bar}\n"
            f"• **Messages:** {db_user.messages_count}\n"
            f"• **HubCoins:** {db_user.hubcoins} 💰\n"
            f"• **Reputation:** {db_user.reputation} 👍\n"
            f"• **Daily Streak:** {db_user.daily_streak or 0} days 🔥\n"
            f"• **Next Level:** in {messages_for_next} messages.\n"
            f"• **VIP Status:** {'Yes 🎖️' if db_user.vip_member else 'No'}\n"
            f"• **Achievements:** {len(db_user.achievements.split(',')) if db_user.achievements else 0} 🏆"
        )
        
        keyboard = [
            [InlineKeyboardButton("« Back", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await query.edit_message_text("Kuch error aaya hai. Thodi der baad try karo.")
    finally:
        session.close()

async def shop_command_with_query(query, context):
    shop_text = (
        "🛒 **ThePromotionHub Shop** 🛒\n\n"
        "Apne HubCoins se yeh items khareedo:\n\n"
        "1. **Title** (1000 Coins) - Ek hafte ke liye custom title.\n"
        "   `/buy title [Your Title]`\n\n"
        "2. **Spotlight** (2500 Coins) - Agle din ke spotlight mein guaranteed jagah.\n"
        "   `/buy spotlight`\n\n"
        "3. **VIP** (10000 Coins) - Permanent VIP status aur special perks.\n"
        "   `/buy vip`\n\n"
        "4. **Name Color** (1500 Coins) - Apne naam ka color change karo.\n"
        "   `/buy color [color]`\n\n"
        "5. **Daily Boost** (500 Coins) - Agle 24 hours ke liye 2x coins milein.\n"
        "   `/buy boost`"
    )
    
    keyboard = [
        [InlineKeyboardButton("« Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(shop_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def help_command_with_query(query, context):
    help_text = (
        "📜 **LevelUp Leo Commands** 📜\n\n"
        "`/stats` - Apni level, coins aur progress dekho.\n"
        "`/coins` - Apne HubCoins ka balance dekho.\n"
        "`/shop` - Dekho ki tum HubCoins se kya khareed sakte ho.\n"
        "`/buy [item]` - Shop se kuch khareedo (e.g., `/buy title`)\n"
        "`/prestige` - Level 100 ke baad special badge ke liye level reset karo.\n"
        "`/daily` - Roz ka reward claim karo.\n"
        "Reply to a message with `/rep` to give reputation to a user."
    )
    
    keyboard = [
        [InlineKeyboardButton("« Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def premium_command_with_query(query, context):
    premium_text = (
        "🌟 **LevelUp Leo Premium** 🌟\n\n"
        "Premium features ke liye abhi available nahi hain, lekin jald hi aane wale hain!\n\n"
        "Interested hain? @ThePromotionHub ko contact karein."
    )
    
    keyboard = [
        [InlineKeyboardButton("« Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(premium_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def start_command_with_query(query, context):
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='stats'),
         InlineKeyboardButton("🛒 Shop", callback_data='shop')],
        [InlineKeyboardButton("🌟 Premium", callback_data='premium'),
         InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Namaste! Main LevelUp Leo hoon. Group mein message karke apni level badhao!",
        reply_markup=reply_markup
    )

# 5. Scheduled Jobs
async def spotlight_feature(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running daily spotlight job...")
    session = Session()
    try:
        # Prioritize users who bought the spotlight
        priority_user = session.query(User).filter(User.spotlight_priority == True).order_by(func.random()).first()
        
        if priority_user:
            selected_user = priority_user
            selected_user.spotlight_priority = False # Reset after use
            logger.info(f"Spotlight priority user found: {selected_user.first_name}")
        else:
            # Select a random active user from the last 7 days
            one_week_ago = datetime.now() - timedelta(days=7)
            active_users = session.query(User).filter(User.last_message_date >= one_week_ago).all()
            if not active_users: 
                logger.info("No active users found for spotlight.")
                return
            selected_user = random.choice(active_users)
            logger.info(f"Spotlight random user found: {selected_user.first_name}")
        
        user_mention = f"@{selected_user.username}" if selected_user.username else selected_user.first_name
        spotlight_text = (
            f"🌟 **Spotlight of the Day: {selected_user.get_display_name()}!** 🌟\n\n"
            f"{selected_user.get_display_name()} has been super active in our community (Level: {selected_user.level}).\n\n"
            f"Let's show some love today—check out their content and drop your feedback! 🚀"
        )
        
        msg = await context.bot.send_message(chat_id=GROUP_ID, text=spotlight_text, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_after_delay(context.bot, GROUP_ID, msg.message_id, 3600))  # Delete after 1 hour
        session.commit()
    except Exception as e:
        logger.error(f"Spotlight Error: {e}")
    finally:
        session.close()

# Database cleanup job
async def cleanup_expired_titles(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running cleanup job for expired titles...")
    session = Session()
    try:
        expired_users = session.query(User).filter(
            User.custom_title_expiry.isnot(None),
            User.custom_title_expiry < datetime.now()
        ).all()
        
        for user in expired_users:
            user.custom_title = ""
            user.custom_title_expiry = None
            logger.info(f"Cleared expired title for user {user.user_id}")
        
        session.commit()
        logger.info(f"Cleared {len(expired_users)} expired titles")
    except Exception as e:
        logger.error(f"Cleanup Error: {e}")
    finally:
        session.close()

# Network error handling
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Check if it's a network error
    if "network" in str(context.error).lower() or "connection" in str(context.error).lower():
        logger.warning("Network error detected, waiting before retrying...")
        await asyncio.sleep(5)  # Wait before retrying

# Health check endpoint for Render
from aiohttp import web

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

# -*- coding: utf-8 -*-
# LevelUp Leo Bot - Fixed Main Function

# ... (पिछला सारा code exactly वैसा ही रखें)

# --- Main Application ---
async def main() -> None:
    # Create the Telegram bot application with connection pooling
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .pool_timeout(30)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Add all command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("prestige", prestige_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("coins", stats_command))
    application.add_handler(CommandHandler("rep", rep_command))
    application.add_handler(CommandHandler("daily", daily_command))

    # Add callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_handler))

    # Add message handler for leveling up
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add handler for new members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Add job queue for scheduled tasks
    job_queue = application.job_queue
    # Run spotlight every 24 hours
    job_queue.run_repeating(spotlight_feature, interval=timedelta(hours=24), first=10)
    # Run cleanup every 6 hours
    job_queue.run_repeating(cleanup_expired_titles, interval=timedelta(hours=6), first=10)

    logger.info("Starting bot...")
    
    # Start web server for health checks
    asyncio.create_task(start_web_server())
    
    # Start the bot
    await application.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    # Run the main function
    asyncio.run(main())
