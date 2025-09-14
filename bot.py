# -*- coding: utf-8 -*-
# Enhanced LevelUp Leo Bot with improved architecture and features

import os
import logging
import random
import asyncio
import time
import aiohttp
import asyncpg
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from contextlib import asynccontextmanager

import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, 
    ChatMemberHandler, filters, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

# --- Enhanced Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Environment variables with validation
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db')
GROUP_ID = int(os.environ.get('GROUP_ID', 0))
PORT = int(os.environ.get('PORT', 8443))
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

if not all([BOT_TOKEN, GEMINI_API_KEY, GROUP_ID]):
    logger.critical("CRITICAL ERROR: Missing required environment variables!")
    exit()

# --- Database Layer with Connection Pooling ---
class Database:
    def __init__(self):
        self.pool = None
        
    async def init(self):
        if DATABASE_URL.startswith('postgresql'):
            self.pool = await asyncpg.create_pool(DATABASE_URL)
            await self.create_tables()
        else:
            logger.warning("Using SQLite - for production, consider PostgreSQL")
            # SQLite fallback implementation would go here
    
    async def create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255) NOT NULL,
                    level INTEGER DEFAULT 0,
                    messages_count INTEGER DEFAULT 0,
                    prestige INTEGER DEFAULT 0,
                    hubcoins INTEGER DEFAULT 10,
                    reputation INTEGER DEFAULT 0,
                    last_message_date TIMESTAMP,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    vip_member BOOLEAN DEFAULT FALSE,
                    custom_title VARCHAR(50) DEFAULT '',
                    custom_title_expiry TIMESTAMP,
                    spotlight_priority BOOLEAN DEFAULT FALSE,
                    daily_streak INTEGER DEFAULT 0,
                    last_daily_date DATE,
                    achievements JSONB DEFAULT '[]'
                )
            ''')
    
    @asynccontextmanager
    async def get_connection(self):
        if self.pool:
            async with self.pool.acquire() as conn:
                yield conn
        else:
            # SQLite fallback
            pass

db = Database()

# --- Cache Layer with Redis ---
class Cache:
    def __init__(self):
        self.redis = None
        
    async def init(self):
        try:
            if REDIS_URL:
                self.redis = await aioredis.from_url(REDIS_URL)
                logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")

cache = Cache()

# --- AI Service with Enhanced Capabilities ---
class AIService:
    def __init__(self):
        self.model = None
        self.chat_sessions = {}
        
    async def init(self):
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            logger.info("Gemini AI configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure Gemini AI: {e}")
    
    async def generate_response(self, prompt: str, context: str = "") -> str:
        if not self.model:
            return "AI service is currently unavailable."
            
        try:
            full_prompt = f"{context}\n\n{prompt}" if context else prompt
            response = await asyncio.to_thread(
                self.model.generate_content, 
                full_prompt,
                safety_settings={'HARASSMENT':'block_none'}
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return "I'm having trouble thinking right now. Please try again later."

ai_service = AIService()

# --- Enhanced User Model ---
class User:
    def __init__(self, record):
        self.user_id = record['user_id']
        self.username = record['username']
        self.first_name = record['first_name']
        self.level = record['level']
        self.messages_count = record['messages_count']
        self.prestige = record['prestige']
        self.hubcoins = record['hubcoins']
        self.reputation = record['reputation']
        self.vip_member = record['vip_member']
        self.custom_title = record['custom_title']
        self.daily_streak = record['daily_streak']
        self.achievements = record['achievements'] or []
    
    def get_display_name(self):
        title = f" [{self.custom_title}]" if self.custom_title else ""
        prestige_badge = '🌟' * self.prestige if self.prestige > 0 else ''
        return f"{self.first_name}{title}{prestige_badge}"
    
    def get_level_progress(self):
        current_req = self.get_level_requirements(self.level)
        next_req = self.get_level_requirements(self.level + 1)
        progress = ((self.messages_count - current_req) / 
                   (next_req - current_req)) * 100 if next_req > current_req else 100
        return min(100, max(0, progress))
    
    @staticmethod
    def get_level_requirements(level: int) -> int:
        if level <= 0: return 0
        if level <= 10: return level * 10
        elif level <= 25: return 100 + (level - 10) * 25
        elif level <= 50: return 475 + (level - 25) * 50
        else: return 1725 + (level - 50) * 100

# --- Enhanced Economy System ---
class EconomySystem:
    def __init__(self):
        self.shop_items = {
            'title': {'price': 1000, 'type': 'customization'},
            'spotlight': {'price': 2500, 'type': 'visibility'},
            'vip': {'price': 10000, 'type': 'membership'},
            'color_name': {'price': 1500, 'type': 'customization'},
            'daily_boost': {'price': 500, 'type': 'boost', 'duration': 24},
        }
    
    async def process_transaction(self, user_id: int, item: str, quantity: int = 1) -> Dict[str, Any]:
        async with db.get_connection() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1', user_id
            )
            if not user:
                return {'success': False, 'message': 'User not found'}
            
            user_obj = User(user)
            item_data = self.shop_items.get(item)
            
            if not item_data:
                return {'success': False, 'message': 'Invalid item'}
            
            total_price = item_data['price'] * quantity
            
            if user_obj.hubcoins < total_price:
                return {
                    'success': False, 
                    'message': f'Not enough coins. Need {total_price}, have {user_obj.hubcoins}'
                }
            
            # Process the purchase
            new_balance = user_obj.hubcoins - total_price
            
            if item == 'vip':
                await conn.execute(
                    'UPDATE users SET hubcoins = $1, vip_member = TRUE WHERE user_id = $2',
                    new_balance, user_id
                )
            elif item == 'title':
                # Title would be handled in the command with additional parameters
                pass
            
            return {'success': True, 'new_balance': new_balance}

economy = EconomySystem()

# --- Enhanced Message Handling with Rate Limiting ---
class MessageProcessor:
    def __init__(self):
        self.user_cooldowns = {}
        self.message_queue = asyncio.Queue()
        
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        current_time = time.time()
        
        # Rate limiting (1 message per second per user)
        if user_id in self.user_cooldowns and current_time - self.user_cooldowns[user_id] < 1:
            return
            
        self.user_cooldowns[user_id] = current_time
        await self.message_queue.put((update, context))
        
        # Process message in background
        asyncio.create_task(self._process_queued_message())

    async def _process_queued_message(self):
        try:
            update, context = await self.message_queue.get()
            await self._handle_message(update, context)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
        finally:
            self.message_queue.task_done()

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Your existing message handling logic here
        pass

message_processor = MessageProcessor()

# --- Enhanced Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db.get_connection() as conn:
        user = await conn.fetchrow(
            'SELECT * FROM users WHERE user_id = $1', 
            update.effective_user.id
        )
        
        if not user:
            await update.message.reply_text("Aap abhi tak register nahi hue hain!")
            return
            
        user_obj = User(user)
        next_level_req = user_obj.get_level_requirements(user_obj.level + 1)
        progress = user_obj.get_level_progress()
        
        # Create a visual progress bar
        progress_bar = "[" + "█" * int(progress / 5) + "░" * (20 - int(progress / 5)) + "]"
        
        stats_text = (
            f"📊 **{user_obj.get_display_name()}'s Stats**\n\n"
            f"• **Level:** {user_obj.level} (Prestige {user_obj.prestige}🌟)\n"
            f"• **Progress to next level:** {progress:.1f}%\n{progress_bar}\n"
            f"• **Messages:** {user_obj.messages_count}\n"
            f"• **HubCoins:** {user_obj.hubcoins} 💰\n"
            f"• **Reputation:** {user_obj.reputation} 👍\n"
            f"• **Daily Streak:** {user_obj.daily_streak} days 🔥\n"
            f"• **VIP Status:** {'Yes 🎖️' if user_obj.vip_member else 'No'}\n"
            f"• **Achievements:** {len(user_obj.achievements)} 🏆"
        )
        
        msg = await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))

# --- Enhanced Shop System with Interactive Menu ---
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- Achievement System ---
class AchievementSystem:
    def __init__(self):
        self.achievements = {
            'first_message': {'name': 'First Words', 'desc': 'Send your first message', 'reward': 50},
            'level_10': {'name': 'Rising Star', 'desc': 'Reach level 10', 'reward': 100},
            'level_50': {'name': 'Half Century', 'desc': 'Reach level 50', 'reward': 500},
            'level_100': {'name': 'Centurion', 'desc': 'Reach level 100', 'reward': 1000},
            'vip': {'name': 'Elite Member', 'desc': 'Purchase VIP status', 'reward': 200},
            'streak_7': {'name': 'Consistent', 'desc': '7-day message streak', 'reward': 150},
            'streak_30': {'name': 'Dedicated', 'desc': '30-day message streak', 'reward': 500},
        }
    
    async def check_achievements(self, user_id: int, achievement_type: str):
        async with db.get_connection() as conn:
            user = await conn.fetchrow(
                'SELECT achievements FROM users WHERE user_id = $1', user_id
            )
            
            if not user or achievement_type in user['achievements']:
                return False
                
            achievement = self.achievements.get(achievement_type)
            if not achievement:
                return False
                
            new_achievements = user['achievements'] + [achievement_type]
            await conn.execute(
                'UPDATE users SET achievements = $1, hubcoins = hubcoins + $2 WHERE user_id = $3',
                new_achievements, achievement['reward'], user_id
            )
            
            return achievement

achievement_system = AchievementSystem()

# --- Daily Reward System ---
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db.get_connection() as conn:
        user = await conn.fetchrow(
            'SELECT * FROM users WHERE user_id = $1', 
            update.effective_user.id
        )
        
        if not user:
            await update.message.reply_text("Aap abhi tak register nahi hue hain!")
            return
            
        user_obj = User(user)
        today = datetime.now().date()
        last_daily = user['last_daily_date']
        
        if last_daily and last_daily.date() == today:
            msg = await update.message.reply_text("Aap aaj ka daily reward already le chuke hain! Kal fir try karein.")
            asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
            return
        
        # Calculate streak
        streak = user_obj.daily_streak
        if last_daily and (today - last_daily.date()).days == 1:
            streak += 1
        else:
            streak = 1
        
        # Calculate reward based on streak
        base_reward = 50
        streak_bonus = min(100, streak * 5)  # Max 100 coin bonus
        total_reward = base_reward + streak_bonus
        
        # Update user
        await conn.execute(
            '''UPDATE users SET hubcoins = hubcoins + $1, 
            daily_streak = $2, last_daily_date = $3 WHERE user_id = $4''',
            total_reward, streak, today, update.effective_user.id
        )
        
        msg = await update.message.reply_text(
            f"🎉 Daily Reward Claimed! 🎉\n"
            f"Aapko mile {total_reward} HubCoins!\n"
            f"Streak: {streak} days\n"
            f"Kal fir aaye aur zyada coins kamayein!"
        )
        asyncio.create_task(delete_message_after_delay(context.bot, update.effective_chat.id, msg.message_id))
        
        # Check for streak achievements
        if streak == 7:
            await achievement_system.check_achievements(update.effective_user.id, 'streak_7')
        elif streak == 30:
            await achievement_system.check_achievements(update.effective_user.id, 'streak_30')

# --- Enhanced Auto-Delete with Priority Queue ---
class MessageScheduler:
    def __init__(self):
        self.pending_deletions = {}
        
    async def schedule_deletion(self, chat_id: int, message_id: int, delay: int = 60, priority: int = 1):
        task = asyncio.create_task(self._delete_after_delay(chat_id, message_id, delay))
        if chat_id not in self.pending_deletions:
            self.pending_deletions[chat_id] = {}
        self.pending_deletions[chat_id][message_id] = task
        
    async def _delete_after_delay(self, chat_id: int, message_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
                data = {"chat_id": chat_id, "message_id": message_id}
                async with session.post(url, json=data) as response:
                    if response.status != 200:
                        logger.error(f"Failed to delete message {message_id}")
        except Exception as e:
            logger.error(f"Error deleting message {message_id}: {e}")
        finally:
            if chat_id in self.pending_deletions and message_id in self.pending_deletions[chat_id]:
                del self.pending_deletions[chat_id][message_id]
    
    async def cancel_deletion(self, chat_id: int, message_id: int):
        if chat_id in self.pending_deletions and message_id in self.pending_deletions[chat_id]:
            self.pending_deletions[chat_id][message_id].cancel()
            del self.pending_deletions[chat_id][message_id]

message_scheduler = MessageScheduler()

# --- Main Application with Enhanced Initialization ---
async def main():
    # Initialize components
    await db.init()
    await cache.init()
    await ai_service.init()
    
    # Create application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .pool_timeout(30)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("daily", daily_command))
    application.add_handler(CommandHandler("prestige", prestige_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_processor.process_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start web server for health checks
    asyncio.create_task(start_web_server())
    
    # Start bot
    logger.info("Bot starting...")
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
