# -*- coding: utf-8 -*-
"""
LevelUp Leo Bot - Professional Edition
A robust, scalable Telegram bot with advanced leveling system and gamification features
Version: 2.0.0
"""

import os
import sys
import logging
import asyncio
import json
import time
import aiohttp
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from contextlib import asynccontextmanager
from functools import wraps
from enum import Enum
import hashlib
import hmac

import google.generativeai as genai
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    BotCommand
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    ContextTypes, 
    ChatMemberHandler, 
    filters, 
    CallbackQueryHandler,
    ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError, NetworkError, TimedOut
from telegram.helpers import escape_markdown

from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    String, 
    Boolean, 
    DateTime, 
    Float,
    func, 
    BigInteger, 
    text, 
    JSON,
    Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.pool import QueuePool

from cachetools import TTLCache
from aiohttp import web
import redis.asyncio as redis

# ==================== Configuration ====================

class Config:
    """Centralized configuration management"""
    
    # Environment variables
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db')
    REDIS_URL = os.environ.get('REDIS_URL')
    GROUP_ID = int(os.environ.get('GROUP_ID', 0))
    PORT = int(os.environ.get('PORT', 8443))
    ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
    
    # Rate limiting
    MAX_MESSAGES_PER_SECOND = 30
    RATE_LIMIT_WINDOW = 60
    
    # Cache settings
    CACHE_TTL = 300  # 5 minutes
    USER_CACHE_SIZE = 1000
    
    # Bot settings
    MESSAGE_DELETE_DELAY = 60  # seconds
    WELCOME_DELETE_DELAY = 120  # seconds
    SPOTLIGHT_DELETE_DELAY = 3600  # 1 hour
    
    # Database settings
    DB_POOL_SIZE = 20
    DB_MAX_OVERFLOW = 40
    DB_POOL_TIMEOUT = 30
    DB_POOL_RECYCLE = 3600
    
    # Validation
    MAX_TITLE_LENGTH = 20
    MAX_MESSAGE_LENGTH = 4096
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        missing = []
        if not cls.BOT_TOKEN:
            missing.append('BOT_TOKEN')
        if not cls.GEMINI_API_KEY:
            missing.append('GEMINI_API_KEY')
        if not cls.GROUP_ID:
            missing.append('GROUP_ID')
        
        if missing:
            raise ValueError(f"Missing critical environment variables: {', '.join(missing)}")

# ==================== Logging Setup ====================

class CustomFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.INFO: grey + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def setup_logging():
    """Configure comprehensive logging"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if Config.ENVIRONMENT == 'development' else logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    
    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        'bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# ==================== Database Models ====================

Base = declarative_base()

class User(Base):
    """Enhanced user model with optimized fields and indexes"""
    __tablename__ = 'users'
    
    # Primary fields
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255), nullable=False)
    
    # Level and progression
    level = Column(Integer, default=0, index=True)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0)
    hubcoins = Column(Integer, default=100)
    reputation = Column(Integer, default=0)
    xp = Column(Integer, default=0)
    
    # Timestamps
    last_message_date = Column(DateTime, index=True)
    join_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # Shop & Perks
    vip_member = Column(Boolean, default=False)
    vip_expiry = Column(DateTime)
    custom_title = Column(String(50), default="")
    custom_title_expiry = Column(DateTime)
    spotlight_priority = Column(Boolean, default=False)
    boost_active = Column(Boolean, default=False)
    boost_expiry = Column(DateTime)
    
    # Streaks and achievements
    daily_streak = Column(Integer, default=0)
    last_daily_date = Column(DateTime)
    achievements = Column(JSON, default=dict)
    badges = Column(JSON, default=list)
    
    # Anti-spam and rate limiting
    message_timestamps = Column(JSON, default=list)
    warnings = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String(255))
    
    # Statistics
    total_xp_earned = Column(Integer, default=0)
    total_coins_earned = Column(Integer, default=0)
    total_coins_spent = Column(Integer, default=0)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_user_level_messages', 'level', 'messages_count'),
        Index('idx_user_activity', 'last_message_date', 'last_active'),
    )
    
    def get_display_name(self):
        """Get formatted display name with badges"""
        title = f" [{self.custom_title}]" if self.custom_title and not self._is_title_expired() else ""
        vip_badge = " 👑" if self.vip_member and not self._is_vip_expired() else ""
        prestige_badge = '⭐' * min(self.prestige, 5) if self.prestige > 0 else ''
        return f"{self.first_name}{title}{vip_badge}{prestige_badge}"
    
    def _is_title_expired(self):
        """Check if custom title has expired"""
        if not self.custom_title_expiry:
            return False
        return datetime.utcnow() > self.custom_title_expiry
    
    def _is_vip_expired(self):
        """Check if VIP status has expired"""
        if not self.vip_expiry:
            return False
        return datetime.utcnow() > self.vip_expiry
    
    def to_dict(self):
        """Convert user to dictionary for caching"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'level': self.level,
            'messages_count': self.messages_count,
            'hubcoins': self.hubcoins,
            'prestige': self.prestige,
            'vip_member': self.vip_member,
            'achievements': self.achievements or {}
        }

# ==================== Database Manager ====================

class DatabaseManager:
    """Robust database connection and session management"""
    
    def __init__(self):
        self.engine = None
        self.Session = None
        self._setup_database()
    
    def _setup_database(self):
        """Setup database with connection pooling and retry logic"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Create engine with optimized settings
                self.engine = create_engine(
                    Config.DATABASE_URL,
                    poolclass=QueuePool,
                    pool_size=Config.DB_POOL_SIZE,
                    max_overflow=Config.DB_MAX_OVERFLOW,
                    pool_timeout=Config.DB_POOL_TIMEOUT,
                    pool_recycle=Config.DB_POOL_RECYCLE,
                    pool_pre_ping=True,  # Verify connections before using
                    echo=Config.ENVIRONMENT == 'development',
                    connect_args={
                        'connect_timeout': 10,
                        'options': '-c statement_timeout=30000'  # 30 second statement timeout
                    } if Config.DATABASE_URL.startswith('postgresql') else {}
                )
                
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                # Create tables
                Base.metadata.create_all(self.engine)
                
                # Setup session factory
                self.Session = scoped_session(sessionmaker(
                    bind=self.engine,
                    expire_on_commit=False
                ))
                
                logger.info("Database connection established successfully")
                return
                
            except SQLAlchemyError as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.critical("Failed to connect to database after maximum retries")
                    raise
    
    @asynccontextmanager
    async def get_session(self):
        """Async context manager for database sessions"""
        session = self.Session()
        try:
            yield session
            await asyncio.to_thread(session.commit)
        except SQLAlchemyError as e:
            await asyncio.to_thread(session.rollback)
            logger.error(f"Database error: {e}")
            raise
        finally:
            await asyncio.to_thread(session.close)
    
    def close(self):
        """Close database connections"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()

# ==================== Cache Manager ====================

class CacheManager:
    """Centralized caching system"""
    
    def __init__(self):
        self.user_cache = TTLCache(maxsize=Config.USER_CACHE_SIZE, ttl=Config.CACHE_TTL)
        self.rate_limit_cache = TTLCache(maxsize=1000, ttl=Config.RATE_LIMIT_WINDOW)
        self.redis_client = None
        self._setup_redis()
    
    async def _setup_redis(self):
        """Setup Redis connection if available"""
        if Config.REDIS_URL:
            try:
                self.redis_client = await redis.from_url(Config.REDIS_URL)
                await self.redis_client.ping()
                logger.info("Redis cache connected successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed, using in-memory cache: {e}")
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user from cache"""
        # Try memory cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]
        
        # Try Redis if available
        if self.redis_client:
            try:
                data = await self.redis_client.get(f"user:{user_id}")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        return None
    
    async def set_user(self, user_id: int, user_data: Dict):
        """Cache user data"""
        self.user_cache[user_id] = user_data
        
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"user:{user_id}",
                    Config.CACHE_TTL,
                    json.dumps(user_data)
                )
            except Exception as e:
                logger.error(f"Redis set error: {e}")
    
    async def check_rate_limit(self, user_id: int) -> bool:
        """Check if user is rate limited"""
        key = f"rate:{user_id}"
        current_count = self.rate_limit_cache.get(key, 0)
        
        if current_count >= Config.MAX_MESSAGES_PER_SECOND:
            return False
        
        self.rate_limit_cache[key] = current_count + 1
        return True

# ==================== Input Validator ====================

class InputValidator:
    """Comprehensive input validation and sanitization"""
    
    @staticmethod
    def validate_title(title: str) -> Tuple[bool, str]:
        """Validate custom title"""
        if not title:
            return False, "Title cannot be empty"
        
        if len(title) > Config.MAX_TITLE_LENGTH:
            return False, f"Title must be {Config.MAX_TITLE_LENGTH} characters or less"
        
        # Check for inappropriate content
        banned_words = ['admin', 'mod', 'owner', 'official']
        if any(word in title.lower() for word in banned_words):
            return False, "Title contains restricted words"
        
        # Sanitize
        title = title.strip()
        if not title.replace(' ', '').isalnum():
            return False, "Title can only contain letters, numbers, and spaces"
        
        return True, title
    
    @staticmethod
    def validate_amount(amount: str) -> Tuple[bool, int]:
        """Validate numeric amount"""
        try:
            value = int(amount)
            if value <= 0:
                return False, 0
            if value > 1000000:  # Max limit
                return False, 0
            return True, value
        except ValueError:
            return False, 0
    
    @staticmethod
    def sanitize_message(text: str) -> str:
        """Sanitize message text"""
        if not text:
            return ""
        
        # Truncate if too long
        if len(text) > Config.MAX_MESSAGE_LENGTH:
            text = text[:Config.MAX_MESSAGE_LENGTH] + "..."
        
        # Escape markdown
        text = escape_markdown(text, version=2)
        
        return text

# ==================== Achievement System ====================

class AchievementManager:
    """Advanced achievement and badge system"""
    
    ACHIEVEMENTS = {
        # Message achievements
        "first_message": {
            "name": "First Words",
            "description": "Send your first message",
            "reward": 50,
            "icon": "🎯"
        },
        "message_100": {
            "name": "Chatterbox",
            "description": "Send 100 messages",
            "reward": 100,
            "icon": "💬"
        },
        "message_1000": {
            "name": "Conversation Master",
            "description": "Send 1000 messages",
            "reward": 500,
            "icon": "🗣️"
        },
        
        # Level achievements
        "level_10": {
            "name": "Rising Star",
            "description": "Reach level 10",
            "reward": 100,
            "icon": "⭐"
        },
        "level_50": {
            "name": "Half Century",
            "description": "Reach level 50",
            "reward": 500,
            "icon": "🌟"
        },
        "level_100": {
            "name": "Centurion",
            "description": "Reach level 100",
            "reward": 1000,
            "icon": "💯"
        },
        
        # Streak achievements
        "streak_7": {
            "name": "Week Warrior",
            "description": "7-day message streak",
            "reward": 150,
            "icon": "🔥"
        },
        "streak_30": {
            "name": "Monthly Master",
            "description": "30-day message streak",
            "reward": 500,
            "icon": "🏆"
        },
        "streak_100": {
            "name": "Century Streak",
            "description": "100-day message streak",
            "reward": 2000,
            "icon": "💎"
        },
        
        # Special achievements
        "vip": {
            "name": "Elite Member",
            "description": "Purchase VIP status",
            "reward": 200,
            "icon": "👑"
        },
        "prestige_1": {
            "name": "Prestige Pioneer",
            "description": "Achieve first prestige",
            "reward": 1000,
            "icon": "🌟"
        },
        "rich": {
            "name": "Wealthy",
            "description": "Accumulate 10,000 coins",
            "reward": 500,
            "icon": "💰"
        }
    }
    
    @classmethod
    async def check_and_award(cls, user: User, achievement_key: str) -> Optional[Dict]:
        """Check and award achievement to user"""
        if not user.achievements:
            user.achievements = {}
        
        # Already has achievement
        if achievement_key in user.achievements:
            return None
        
        achievement = cls.ACHIEVEMENTS.get(achievement_key)
        if not achievement:
            return None
        
        # Award achievement
        user.achievements[achievement_key] = {
            'earned_at': datetime.utcnow().isoformat(),
            'name': achievement['name'],
            'icon': achievement['icon']
        }
        user.hubcoins += achievement['reward']
        user.total_coins_earned += achievement['reward']
        
        logger.info(f"User {user.user_id} earned achievement: {achievement_key}")
        return achievement
    
    @classmethod
    async def check_all_achievements(cls, user: User) -> List[Dict]:
        """Check all possible achievements for a user"""
        earned = []
        
        # Message achievements
        if user.messages_count >= 1:
            achievement = await cls.check_and_award(user, 'first_message')
            if achievement:
                earned.append(achievement)
        
        if user.messages_count >= 100:
            achievement = await cls.check_and_award(user, 'message_100')
            if achievement:
                earned.append(achievement)
        
        if user.messages_count >= 1000:
            achievement = await cls.check_and_award(user, 'message_1000')
            if achievement:
                earned.append(achievement)
        
        # Level achievements
        if user.level >= 10:
            achievement = await cls.check_and_award(user, 'level_10')
            if achievement:
                earned.append(achievement)
        
        if user.level >= 50:
            achievement = await cls.check_and_award(user, 'level_50')
            if achievement:
                earned.append(achievement)
        
        if user.level >= 100:
            achievement = await cls.check_and_award(user, 'level_100')
            if achievement:
                earned.append(achievement)
        
        # Streak achievements
        if user.daily_streak >= 7:
            achievement = await cls.check_and_award(user, 'streak_7')
            if achievement:
                earned.append(achievement)
        
        if user.daily_streak >= 30:
            achievement = await cls.check_and_award(user, 'streak_30')
            if achievement:
                earned.append(achievement)
        
        if user.daily_streak >= 100:
            achievement = await cls.check_and_award(user, 'streak_100')
            if achievement:
                earned.append(achievement)
        
        # Wealth achievement
        if user.hubcoins >= 10000:
            achievement = await cls.check_and_award(user, 'rich')
            if achievement:
                earned.append(achievement)
        
        # Prestige achievement
        if user.prestige >= 1:
            achievement = await cls.check_and_award(user, 'prestige_1')
            if achievement:
                earned.append(achievement)
        
        return earned

# ==================== Level System ====================

class LevelSystem:
    """Advanced leveling and progression system"""
    
    # Level stickers mapping
    LEVEL_STICKERS = {
        1: ["CAACAgEAAxkBAAECZohow8nXm9oFdxnWioDIioN6859S4wACpQIAAkb-8Ec467BfJxQ8djYE"],
        5: ["CAACAgEAAxkBAAECaP1oxRfMvKFVsuGdqgFtWL8LoqKjMQACBQMAAnNOIERFC6_h0W0SgDYE"],
        10: ["CAACAgEAAxkBAAECaQFoxRf1T3qdVXZN623-6KUJarP_hQACfQMAAj7OWETdjsszH42-rzYE"],
        25: ["CAACAgIAAxkBAAECaQVoxRgnf9Tl_egizv2IzRq-p4JDPgACWDEAAvTKMEpYpE1ML4rwgTYE"],
        50: ["CgACAgQAAxkBAAECaQdoxRidErmqz3qB1miEt6Bf38ty2QACVwMAAolPBFMwDn_gBXkQejYE"],
        75: ["CAACAgUAAxkBAAECaQ9oxRkWl7-xcGPLi-lwXgABsioAAbKwAAIzDgAC5j65V5cS4rkdBo1VNgQ"],
        100: ["CAACAgIAAxkBAAECaRVoxRnUU7Q1SqXKZmqOZWSuAAHeGBMAAuENAAIxDJhKsojdm6OziV42BA"]
    }
    
    @staticmethod
    def calculate_xp_for_level(level: int) -> int:
        """Calculate total XP needed for a specific level"""
        if level <= 0:
            return 0
        elif level <= 10:
            return level * 100
        elif level <= 25:
            return 1000 + (level - 10) * 250
        elif level <= 50:
            return 4750 + (level - 25) * 500
        elif level <= 100:
            return 17250 + (level - 50) * 1000
        else:
            return 67250 + (level - 100) * 2000
    
    @staticmethod
    def calculate_level_from_xp(xp: int) -> int:
        """Calculate level from total XP"""
        level = 0
        while xp >= LevelSystem.calculate_xp_for_level(level + 1):
            level += 1
        return level
    
    @staticmethod
    def get_progress_bar(current_xp: int, current_level: int) -> str:
        """Generate visual progress bar"""
        current_level_xp = LevelSystem.calculate_xp_for_level(current_level)
        next_level_xp = LevelSystem.calculate_xp_for_level(current_level + 1)
        
        progress = (current_xp - current_level_xp) / (next_level_xp - current_level_xp) * 100
        progress = max(0, min(100, progress))
        
        filled = int(progress / 5)
        empty = 20 - filled
        
        return f"[{'█' * filled}{'░' * empty}] {progress:.1f}%"
    
    @staticmethod
    def get_level_title(level: int) -> str:
        """Get title based on level"""
        titles = {
            0: "Newbie",
            10: "Apprentice",
            25: "Member",
            50: "Veteran",
            75: "Expert",
            100: "Master",
            150: "Grand Master",
            200: "Legend"
        }
        
        for min_level in sorted(titles.keys(), reverse=True):
            if level >= min_level:
                return titles[min_level]
        
        return "Newbie"

# ==================== Message Handler ====================

class MessageProcessor:
    """Process and handle user messages"""
    
    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        self.db = db_manager
        self.cache = cache_manager
        self.gemini_model = self._setup_gemini()
    
    def _setup_gemini(self):
        """Setup Gemini AI model"""
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini AI configured successfully")
            return model
        except Exception as e:
            logger.error(f"Failed to configure Gemini AI: {e}")
            return None
    
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process incoming message and update user stats"""
        if not update.message or not update.message.from_user:
            return
        
        if update.effective_chat.id != Config.GROUP_ID:
            return
        
        user_id = update.effective_user.id
        
        # Check rate limiting
        if not await self.cache.check_rate_limit(user_id):
            logger.warning(f"User {user_id} rate limited")
            return
        
        async with self.db.get_session() as session:
            try:
                # Get or create user
                user = await self._get_or_create_user(session, update.effective_user)
                
                # Update user stats
                old_level = user.level
                user.messages_count += 1
                user.last_message_date = datetime.utcnow()
                user.last_active = datetime.utcnow()
                
                # Calculate XP gain
                base_xp = random.randint(10, 25)
                if user.boost_active and user.boost_expiry > datetime.utcnow():
                    base_xp *= 2
                
                user.xp += base_xp
                user.total_xp_earned += base_xp
                
                # Calculate coins gain
                base_coins = random.randint(1, 5)
                if user.vip_member and (not user.vip_expiry or user.vip_expiry > datetime.utcnow()):
                    base_coins *= 2
                
                user.hubcoins += base_coins
                user.total_coins_earned += base_coins
                
                # Check for level up
                new_level = LevelSystem.calculate_level_from_xp(user.xp)
                level_up_occurred = new_level > old_level
                
                if level_up_occurred:
                    user.level = new_level
                    # Bonus rewards for leveling up
                    level_bonus = new_level * 50
                    user.hubcoins += level_bonus
                    user.total_coins_earned += level_bonus
                    
                    # Send level up message
                    await self._send_level_up_message(update, context, user, new_level)
                
                # Check achievements
                earned_achievements = await AchievementManager.check_all_achievements(user)
                if earned_achievements:
                    await self._notify_achievements(update, context, earned_achievements)
                
                # Update cache
                await self.cache.set_user(user_id, user.to_dict())
                
                # Auto-delete message after delay
                asyncio.create_task(
                    self._delete_message_after_delay(
                        context.bot,
                        update.effective_chat.id,
                        update.message.message_id
                    )
                )
                
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}: {e}")
    
    async def _get_or_create_user(self, session, telegram_user):
        """Get or create user in database"""
        user = await asyncio.to_thread(
            session.query(User).filter(User.user_id == telegram_user.id).first
        )
        
        if not user:
            user = User(
                user_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name or "User"
            )
            session.add(user)
            logger.info(f"Created new user: {telegram_user.id}")
        
        return user
    
    async def _send_level_up_message(self, update, context, user, level):
        """Send level up notification"""
        user_mention = f"@{user.username}" if user.username else user.first_name
        
        # Generate message using AI or fallback
        if self.gemini_model:
            try:
                prompt = f"Write a very short (max 2 lines) congratulations message for {user_mention} reaching Level {level}. Be enthusiastic and use emojis."
                response = await asyncio.to_thread(
                    self.gemini_model.generate_content,
                    prompt
                )
                message = response.text.strip()
            except Exception as e:
                logger.error(f"Gemini error: {e}")
                message = f"🎉 GG {user_mention}! Level {level} achieved! Keep grinding! 🚀"
        else:
            messages = [
                f"🎉 {user_mention} just hit Level {level}! Absolute legend! 🔥",
                f"⚡ Level {level} unlocked! {user_mention} is on fire! 🚀",
                f"👑 {user_mention} reached Level {level}! Built different! 💪",
                f"🌟 Big W! {user_mention} is now Level {level}! 🎊",
            ]
            message = random.choice(messages)
        
        msg = await update.message.reply_text(message)
        
        # Send sticker if available for this level
        if level in LevelSystem.LEVEL_STICKERS:
            sticker_id = random.choice(LevelSystem.LEVEL_STICKERS[level])
            sticker_msg = await update.message.reply_sticker(sticker_id)
            asyncio.create_task(
                self._delete_message_after_delay(
                    context.bot,
                    update.effective_chat.id,
                    sticker_msg.message_id
                )
            )
        
        asyncio.create_task(
            self._delete_message_after_delay(
                context.bot,
                update.effective_chat.id,
                msg.message_id
            )
        )
    
    async def _notify_achievements(self, update, context, achievements):
        """Notify user about earned achievements"""
        for achievement in achievements:
            message = (
                f"🏆 **Achievement Unlocked!**\n"
                f"{achievement['icon']} {achievement['name']}\n"
                f"_{achievement['description']}_\n"
                f"Reward: {achievement['reward']} coins"
            )
            msg = await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN
            )
            asyncio.create_task(
                self._delete_message_after_delay(
                    context.bot,
                    update.effective_chat.id,
                    msg.message_id,
                    delay=30
                )
            )
    
    async def _delete_message_after_delay(self, bot, chat_id, message_id, delay=None):
        """Delete message after specified delay"""
        if delay is None:
            delay = Config.MESSAGE_DELETE_DELAY
        
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"Deleted message {message_id}")
        except BadRequest as e:
            if "Message to delete not found" not in str(e):
                logger.error(f"Error deleting message {message_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error deleting message {message_id}: {e}")

# ==================== Command Handlers ====================

class CommandHandlers:
    """All bot command handlers"""
    
    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        self.db = db_manager
        self.cache = cache_manager
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        keyboard = [
            [
                InlineKeyboardButton("📊 Stats", callback_data='stats'),
                InlineKeyboardButton("🛍️ Shop", callback_data='shop')
            ],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard'),
                InlineKeyboardButton("🎯 Achievements", callback_data='achievements')
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
                InlineKeyboardButton("ℹ️ Help", callback_data='help')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            "🎮 **Welcome to LevelUp Leo!** 🎮\n\n"
            "Level up by chatting in the group!\n"
            "Earn coins, unlock achievements, and become a legend!\n\n"
            "Choose an option below to get started:"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        user_id = update.effective_user.id
        
        # Try cache first
        cached_user = await self.cache.get_user(user_id)
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(User).filter(User.user_id == user_id).first
            )
            
            if not user:
                await update.message.reply_text("You haven't started yet! Send a message in the group first.")
                return
            
            # Generate stats message
            progress_bar = LevelSystem.get_progress_bar(user.xp, user.level)
            level_title = LevelSystem.get_level_title(user.level)
            
            stats_text = (
                f"📊 **{user.get_display_name()}'s Stats**\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"**Rank:** {level_title}\n"
                f"**Level:** {user.level} {'⭐' * min(user.prestige, 5)}\n"
                f"**XP:** {user.xp:,} / {LevelSystem.calculate_xp_for_level(user.level + 1):,}\n"
                f"**Progress:** {progress_bar}\n\n"
                f"**💰 Coins:** {user.hubcoins:,}\n"
                f"**💬 Messages:** {user.messages_count:,}\n"
                f"**👍 Reputation:** {user.reputation:,}\n"
                f"**🔥 Daily Streak:** {user.daily_streak or 0} days\n"
                f"**🏆 Achievements:** {len(user.achievements or {})}\n\n"
                f"**Status:**\n"
            )
            
            # Add status badges
            if user.vip_member and (not user.vip_expiry or user.vip_expiry > datetime.utcnow()):
                stats_text += "• 👑 VIP Member\n"
            if user.boost_active and user.boost_expiry > datetime.utcnow():
                stats_text += "• ⚡ XP Boost Active\n"
            if user.custom_title and (not user.custom_title_expiry or user.custom_title_expiry > datetime.utcnow()):
                stats_text += f"• 🏷️ Title: {user.custom_title}\n"
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Claim daily reward"""
        user_id = update.effective_user.id
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(User).filter(User.user_id == user_id).first
            )
            
            if not user:
                await update.message.reply_text("You need to send a message in the group first!")
                return
            
            today = datetime.utcnow().date()
            last_daily = user.last_daily_date.date() if user.last_daily_date else None
            
            if last_daily == today:
                time_until_reset = datetime.combine(
                    today + timedelta(days=1),
                    datetime.min.time()
                ) - datetime.utcnow()
                hours = int(time_until_reset.total_seconds() // 3600)
                minutes = int((time_until_reset.total_seconds() % 3600) // 60)
                
                await update.message.reply_text(
                    f"⏰ Daily reward already claimed!\n"
                    f"Come back in {hours}h {minutes}m"
                )
                return
            
            # Calculate streak
            if last_daily and (today - last_daily).days == 1:
                user.daily_streak = (user.daily_streak or 0) + 1
            else:
                user.daily_streak = 1
            
            # Calculate rewards
            base_reward = 100
            streak_bonus = min(500, user.daily_streak * 10)
            vip_bonus = 100 if user.vip_member else 0
            total_reward = base_reward + streak_bonus + vip_bonus
            
            # Award rewards
            user.hubcoins += total_reward
            user.total_coins_earned += total_reward
            user.last_daily_date = datetime.utcnow()
            
            # Check streak achievements
            await AchievementManager.check_all_achievements(user)
            
            await update.message.reply_text(
                f"🎁 **Daily Reward Claimed!**\n\n"
                f"Base reward: {base_reward} coins\n"
                f"Streak bonus (Day {user.daily_streak}): {streak_bonus} coins\n"
                f"{f'VIP bonus: {vip_bonus} coins' if vip_bonus else ''}\n"
                f"**Total: {total_reward} coins**\n\n"
                f"🔥 Current streak: {user.daily_streak} days"
            )
    
    async def shop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display shop with items"""
        shop_text = (
            "🛍️ **LevelUp Shop**\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "**Available Items:**\n\n"
            "**1. 🏷️ Custom Title** - 1,000 coins\n"
            "   `/buy title [Your Title]`\n"
            "   _Display a custom title for 7 days_\n\n"
            "**2. ⚡ XP Boost** - 500 coins\n"
            "   `/buy boost`\n"
            "   _Double XP for 24 hours_\n\n"
            "**3. 🌟 Spotlight Priority** - 2,500 coins\n"
            "   `/buy spotlight`\n"
            "   _Guaranteed spotlight feature_\n\n"
            "**4. 👑 VIP Status** - 10,000 coins\n"
            "   `/buy vip`\n"
            "   _30 days of VIP benefits_\n\n"
            "**5. 🎲 Mystery Box** - 1,000 coins\n"
            "   `/buy mystery`\n"
            "   _Random rewards!_\n\n"
            "**6. 🔄 Name Change** - 500 coins\n"
            "   `/buy namechange [New Name]`\n"
            "   _Change your display name_"
        )
        
        await update.message.reply_text(
            shop_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle shop purchases"""
        if not context.args:
            await update.message.reply_text("Usage: `/buy [item] [options]`")
            return
        
        item = context.args.lower()
        user_id = update.effective_user.id
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(User).filter(User.user_id == user_id).first
            )
            
            if not user:
                await update.message.reply_text("You need to send a message in the group first!")
                return
            
            # Process different items
            if item == "title":
                await self._buy_title(update, context, user, session)
            elif item == "boost":
                await self._buy_boost(update, context, user, session)
            elif item == "spotlight":
                await self._buy_spotlight(update, context, user, session)
            elif item == "vip":
                await self._buy_vip(update, context, user, session)
            elif item == "mystery":
                await self._buy_mystery(update, context, user, session)
            elif item == "namechange":
                await self._buy_namechange(update, context, user, session)
            else:
                await update.message.reply_text("❌ Unknown item! Check `/shop` for available items.")
    
    async def _buy_title(self, update, context, user, session):
        """Purchase custom title"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/buy title [Your Title]`")
            return
        
        title = " ".join(context.args[1:])
        is_valid, clean_title = InputValidator.validate_title(title)
        
        if not is_valid:
            await update.message.reply_text(f"❌ {clean_title}")  # clean_title contains error message
            return
        
        if user.hubcoins < 1000:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 1,000 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 1000
        user.total_coins_spent += 1000
        user.custom_title = clean_title
        user.custom_title_expiry = datetime.utcnow() + timedelta(days=7)
        
        await update.message.reply_text(
            f"✅ **Title Purchased!**\n"
            f"Your new title: [{clean_title}]\n"
            f"Valid for 7 days\n"
            f"Remaining coins: {user.hubcoins}"
        )
    
    async def _buy_boost(self, update, context, user, session):
        """Purchase XP boost"""
        if user.hubcoins < 500:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 500 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 500
        user.total_coins_spent += 500
        user.boost_active = True
        user.boost_expiry = datetime.utcnow() + timedelta(hours=24)
        
        await update.message.reply_text(
            f"⚡ **XP Boost Activated!**\n"
            f"You'll earn 2x XP for the next 24 hours!\n"
            f"Remaining coins: {user.hubcoins}"
        )
    
    async def _buy_vip(self, update, context, user, session):
        """Purchase VIP status"""
        if user.hubcoins < 10000:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 10,000 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 10000
        user.total_coins_spent += 10000
        user.vip_member = True
        user.vip_expiry = datetime.utcnow() + timedelta(days=30)
        
        # Award VIP achievement
        achievement = await AchievementManager.check_and_award(user, 'vip')
        
        await update.message.reply_text(
            f"👑 **Welcome to VIP!**\n\n"
            f"Benefits:\n"
            f"• 2x coins from messages\n"
            f"• Exclusive VIP badge\n"
            f"• Daily bonus boost\n"
            f"• Priority support\n\n"
            f"Valid for 30 days\n"
            f"Remaining coins: {user.hubcoins}"
        )
    
    async def _buy_mystery(self, update, context, user, session):
        """Purchase mystery box with random rewards"""
        if user.hubcoins < 1000:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 1,000 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 1000
        user.total_coins_spent += 1000
        
        # Random rewards
        rewards = []
        
        # Coins (70% chance)
        if random.random() < 0.7:
            coin_reward = random.choice([500, 750, 1000, 1500, 2000, 5000])
            user.hubcoins += coin_reward
            user.total_coins_earned += coin_reward
            rewards.append(f"💰 {coin_reward} coins")
        
        # XP (50% chance)
        if random.random() < 0.5:
            xp_reward = random.randint(100, 500)
            user.xp += xp_reward
            user.total_xp_earned += xp_reward
            rewards.append(f"⭐ {xp_reward} XP")
        
        # Temporary boost (20% chance)
        if random.random() < 0.2:
            user.boost_active = True
            user.boost_expiry = datetime.utcnow() + timedelta(hours=12)
            rewards.append("⚡ 12-hour XP boost")
        
        # Reputation (30% chance)
        if random.random() < 0.3:
            rep_reward = random.randint(5, 20)
            user.reputation += rep_reward
            rewards.append(f"👍 {rep_reward} reputation")
        
        if not rewards:
            # Guarantee at least something
            user.hubcoins += 500
            rewards.append("💰 500 coins (consolation prize)")
        
        await update.message.reply_text(
            f"🎲 **Mystery Box Opened!**\n\n"
            f"You received:\n" + "\n".join(f"• {reward}" for reward in rewards) +
            f"\n\nRemaining coins: {user.hubcoins}"
        )
    
    async def _buy_spotlight(self, update, context, user, session):
        """Purchase spotlight priority"""
        if user.hubcoins < 2500:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 2,500 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 2500
        user.total_coins_spent += 2500
        user.spotlight_priority = True
        
        await update.message.reply_text(
            f"🌟 **Spotlight Priority Purchased!**\n"
            f"You'll be featured in the next spotlight!\n"
            f"Remaining coins: {user.hubcoins}"
        )
    
    async def _buy_namechange(self, update, context, user, session):
        """Change display name"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/buy namechange [New Name]`")
            return
        
        new_name = " ".join(context.args[1:])[:50]  # Max 50 chars
        
        if user.hubcoins < 500:
            await update.message.reply_text(
                f"❌ Insufficient coins! You need 500 coins.\n"
                f"Your balance: {user.hubcoins} coins"
            )
            return
        
        user.hubcoins -= 500
        user.total_coins_spent += 500
        user.first_name = new_name
        
        await update.message.reply_text(
            f"✅ **Name Changed!**\n"
            f"Your new name: {new_name}\n"
            f"Remaining coins: {user.hubcoins}"
        )
    
    async def prestige(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle prestige system"""
        user_id = update.effective_user.id
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(User).filter(User.user_id == user_id).first
            )
            
            if not user:
                await update.message.reply_text("You need to send a message in the group first!")
                return
            
            if user.level < 100:
                await update.message.reply_text(
                    f"❌ You need to reach Level 100 to prestige!\n"
                    f"Current level: {user.level}"
                )
                return
            
            # Confirm prestige
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm Prestige", callback_data=f"prestige_confirm_{user_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="prestige_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            prestige_rewards = 1000 * (user.prestige + 1)
            
            await update.message.reply_text(
                f"⚠️ **Prestige Confirmation**\n\n"
                f"Are you sure you want to prestige?\n\n"
                f"**You will lose:**\n"
                f"• Your current level (back to 1)\n"
                f"• Your current XP\n\n"
                f"**You will gain:**\n"
                f"• Prestige level {user.prestige + 1} ⭐\n"
                f"• {prestige_rewards} coins\n"
                f"• Permanent prestige badge\n"
                f"• Increased rewards multiplier",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show server leaderboard"""
        async with self.db.get_session() as session:
            # Get top users by level
            top_by_level = await asyncio.to_thread(
                lambda: session.query(User)
                .order_by(User.prestige.desc(), User.level.desc(), User.xp.desc())
                .limit(10)
                .all()
            )
            
            # Get top users by coins
            top_by_coins = await asyncio.to_thread(
                lambda: session.query(User)
                .order_by(User.hubcoins.desc())
                .limit(5)
                .all()
            )
            
            # Format leaderboard
            leaderboard_text = "🏆 **Server Leaderboard**\n"
            leaderboard_text += "━━━━━━━━━━━━━━━━━\n\n"
            leaderboard_text += "**Top Players by Level:**\n"
            
            medals = ["🥇", "🥈", "🥉"]
            
            for i, user in enumerate(top_by_level, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                prestige_stars = "⭐" * min(user.prestige, 5) if user.prestige > 0 else ""
                leaderboard_text += f"{medal} {user.first_name[:20]} - Lvl {user.level} {prestige_stars}\n"
            
            leaderboard_text += "\n**Richest Players:**\n"
            
            for i, user in enumerate(top_by_coins, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                le
                
