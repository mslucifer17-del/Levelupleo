"""
LevelUp Leo Bot - Production Ready Version
Fixed for Render deployment with proper error handling
"""

import os
import json
import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union
from contextlib import asynccontextmanager

import aiohttp
from aiohttp import web
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    CallbackQueryHandler, filters
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

# SQLAlchemy imports
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, 
    func, BigInteger, text, Float, JSON, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session as SQLSession
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.pool import NullPool, QueuePool

# ==================== Configuration ====================

@dataclass
class BotConfig:
    """Bot configuration with validation and defaults"""
    bot_token: str
    gemini_api_key: str
    database_url: str
    group_id: int
    port: int
    environment: str = "production"
    log_level: str = "INFO"
    max_retries: int = 5
    retry_delay: int = 2
    message_delete_delay: int = 60
    spotlight_interval_hours: int = 24
    cleanup_interval_hours: int = 6
    use_database: bool = True
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Create config from environment variables with validation"""
        # Required vars for basic functionality
        bot_token = os.environ.get('BOT_TOKEN')
        gemini_api_key = os.environ.get('GEMINI_API_KEY', 'dummy_key')  # Optional
        group_id = os.environ.get('GROUP_ID')
        
        if not bot_token:
            raise ValueError("BOT_TOKEN is required")
        
        # Handle DATABASE_URL properly
        database_url = os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db')
        
        # Fix for Render PostgreSQL URLs
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # For internal Render database URLs, use the correct format
        if 'dpg-' in database_url and '-a' in database_url:
            # This is likely an internal Render database hostname
            # Try to use the external URL if available
            database_url_external = os.environ.get('DATABASE_URL_EXTERNAL', database_url)
            if database_url_external != database_url:
                database_url = database_url_external
                if database_url.startswith('postgres://'):
                    database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        return cls(
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            database_url=database_url,
            group_id=int(group_id) if group_id else 0,
            port=int(os.environ.get('PORT', 8443)),
            environment=os.environ.get('ENVIRONMENT', 'production'),
            log_level=os.environ.get('LOG_LEVEL', 'INFO'),
            use_database=os.environ.get('USE_DATABASE', 'true').lower() == 'true'
        )

# ==================== Logging Setup ====================

class BotLogger:
    """Centralized logging configuration"""
    
    @staticmethod
    def setup(config: BotConfig) -> logging.Logger:
        """Setup structured logging with proper formatting"""
        log_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File handler
        file_handler = logging.FileHandler("bot.log", encoding='utf-8')
        file_handler.setFormatter(log_format)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        
        # Setup logger
        logger = logging.getLogger(__name__)
        logger.setLevel(getattr(logging, config.log_level))
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

# ==================== Database Models ====================

Base = declarative_base()

class UserModel(Base):
    """User model with proper indexes"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255), nullable=False)
    
    # Leveling System
    level = Column(Integer, default=0, index=True)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0)
    experience_points = Column(Integer, default=0)
    
    # Economy
    hubcoins = Column(Integer, default=10)
    reputation = Column(Integer, default=0)
    
    # Activity
    last_message_date = Column(DateTime, index=True)
    join_date = Column(DateTime, default=datetime.utcnow)
    daily_streak = Column(Integer, default=0)
    last_daily_date = Column(DateTime)
    
    # Premium
    vip_member = Column(Boolean, default=False)
    custom_title = Column(String(50), default="")
    custom_title_expiry = Column(DateTime)
    spotlight_priority = Column(Boolean, default=False)
    
    # JSON fields
    achievements = Column(JSON, default=list)
    stats = Column(JSON, default=dict)
    
    def get_display_name(self) -> str:
        """Get formatted display name"""
        title = f" [{self.custom_title}]" if self.custom_title else ""
        prestige_badge = '🌟' * self.prestige if self.prestige > 0 else ''
        vip_badge = ' 👑' if self.vip_member else ''
        return f"{self.first_name}{title}{prestige_badge}{vip_badge}"

# ==================== In-Memory Storage Fallback ====================

class InMemoryUserStore:
    """In-memory storage as fallback when database is unavailable"""
    
    def __init__(self):
        self.users: Dict[int, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user from memory store"""
        return self.users.get(user_id)
    
    def create_user(self, user_id: int, username: str, first_name: str) -> Dict[str, Any]:
        """Create user in memory store"""
        user_data = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'level': 0,
            'messages_count': 0,
            'prestige': 0,
            'experience_points': 0,
            'hubcoins': 10,
            'reputation': 0,
            'last_message_date': datetime.utcnow(),
            'join_date': datetime.utcnow(),
            'daily_streak': 0,
            'last_daily_date': None,
            'vip_member': False,
            'custom_title': '',
            'custom_title_expiry': None,
            'spotlight_priority': False,
            'achievements': [],
            'stats': {}
        }
        self.users[user_id] = user_data
        self.logger.info(f"Created in-memory user: {user_id}")
        return user_data
    
    def update_user(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Update user in memory store"""
        if user_id in self.users:
            self.users[user_id].update(updates)
            return True
        return False
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users from memory store"""
        return list(self.users.values())

# ==================== Database Manager ====================

class DatabaseManager:
    """Database manager with fallback to in-memory storage"""
    
    def __init__(self, config: BotConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.engine = None
        self.session_factory = None
        self.in_memory_store = InMemoryUserStore()
        self.use_memory = False
        
        if config.use_database:
            self._initialize_database()
        else:
            self.use_memory = True
            self.logger.warning("Database disabled, using in-memory storage")
    
    def _initialize_database(self) -> None:
        """Initialize database with proper retry logic"""
        for attempt in range(self.config.max_retries):
            try:
                self.logger.info(f"Database connection attempt {attempt + 1}/{self.config.max_retries}")
                
                # Configure connection based on database type
                if 'postgresql' in self.config.database_url or 'postgres' in self.config.database_url:
                    # PostgreSQL configuration
                    pool_class = QueuePool
                    pool_args = {
                        'pool_size': 5,
                        'max_overflow': 10,
                        'pool_timeout': 30,
                        'pool_recycle': 1800,
                        'pool_pre_ping': True,  # Enable connection health checks
                    }
                    connect_args = {
                        'connect_timeout': 10,
                        'options': '-c statement_timeout=30000'  # 30 second statement timeout
                    }
                else:
                    # SQLite configuration
                    pool_class = NullPool
                    pool_args = {}
                    connect_args = {'check_same_thread': False}
                
                # Create engine
                self.engine = create_engine(
                    self.config.database_url,
                    poolclass=pool_class,
                    connect_args=connect_args,
                    echo=False,  # Set to True for debugging
                    **pool_args
                )
                
                # Test connection
                with self.engine.connect() as conn:
                    result = conn.execute(text("SELECT 1"))
                    result.fetchone()
                
                # Create session factory
                self.session_factory = sessionmaker(bind=self.engine)
                
                # Create tables
                Base.metadata.create_all(self.engine)
                
                self.logger.info("Database initialized successfully")
                return
                
            except (SQLAlchemyError, OperationalError) as e:
                self.logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.info(f"Waiting {delay} seconds before retry...")
                    time.sleep(delay)  # Use blocking sleep here since we're in __init__
                else:
                    self.logger.error("Failed to connect to database after all retries")
                    self.logger.warning("Falling back to in-memory storage")
                    self.use_memory = True
                    return
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session or None if using in-memory storage"""
        if self.use_memory:
            yield None
        else:
            session = self.session_factory()
            try:
                yield session
                await asyncio.to_thread(session.commit)
            except Exception as e:
                await asyncio.to_thread(session.rollback)
                self.logger.error(f"Database session error: {e}")
                raise
            finally:
                await asyncio.to_thread(session.close)
    
    def get_sync_session(self):
        """Get synchronous database session for initialization"""
        if self.use_memory:
            return None
        return self.session_factory()

# ==================== User Service ====================

class UserService:
    """Service for user operations with fallback support"""
    
    def __init__(self, db_manager: DatabaseManager, logger: logging.Logger):
        self.db = db_manager
        self.logger = logger
    
    async def get_or_create_user(self, user_data) -> Union[UserModel, Dict[str, Any]]:
        """Get or create user with fallback to in-memory storage"""
        if self.db.use_memory:
            # Use in-memory storage
            user = self.db.in_memory_store.get_user(user_data.id)
            if not user:
                user = self.db.in_memory_store.create_user(
                    user_data.id,
                    user_data.username,
                    user_data.first_name or "User"
                )
            return user
        
        # Use database
        async with self.db.get_session() as session:
            if session is None:
                # Fallback to in-memory if session is None
                return await self.get_or_create_user(user_data)
            
            user = await asyncio.to_thread(
                session.query(UserModel).filter(UserModel.user_id == user_data.id).first
            )
            
            if not user:
                user = UserModel(
                    user_id=user_data.id,
                    username=user_data.username,
                    first_name=user_data.first_name or "User",
                    stats={"total_commands": 0, "total_coins_earned": 0}
                )
                session.add(user)
                await asyncio.to_thread(session.commit)
                self.logger.info(f"Created new user: {user_data.id}")
            
            return user
    
    async def update_user_activity(self, user_id: int) -> Optional[int]:
        """Update user activity and check for level up"""
        if self.db.use_memory:
            # Handle in-memory updates
            user = self.db.in_memory_store.get_user(user_id)
            if not user:
                return None
            
            user['messages_count'] += 1
            user['last_message_date'] = datetime.utcnow()
            user['hubcoins'] += random.randint(1, 3)
            user['experience_points'] += random.randint(5, 15)
            
            # Check for level up
            old_level = user['level']
            new_level = self.calculate_level(user['experience_points'])
            
            if new_level > old_level:
                user['level'] = new_level
                user['hubcoins'] += new_level * 10
                self.db.in_memory_store.update_user(user_id, user)
                return new_level
            
            self.db.in_memory_store.update_user(user_id, user)
            return None
        
        # Use database
        async with self.db.get_session() as session:
            if session is None:
                return None
            
            user = await asyncio.to_thread(
                session.query(UserModel).filter(UserModel.user_id == user_id).first
            )
            
            if not user:
                return None
            
            user.messages_count += 1
            user.last_message_date = datetime.utcnow()
            user.hubcoins += random.randint(1, 3)
            user.experience_points += random.randint(5, 15)
            
            # Check for level up
            old_level = user.level
            new_level = self.calculate_level(user.experience_points)
            
            if new_level > old_level:
                user.level = new_level
                user.hubcoins += new_level * 10
                await asyncio.to_thread(session.commit)
                return new_level
            
            await asyncio.to_thread(session.commit)
            return None
    
    @staticmethod
    def calculate_level(experience: int) -> int:
        """Calculate level from experience"""
        import math
        if experience <= 0:
            return 0
        return int(math.sqrt(experience / 50))

# ==================== Command Handlers ====================

class StatsCommandHandler:
    """Handler for stats command"""
    
    def __init__(self, services: Dict[str, Any], config: BotConfig, logger: logging.Logger):
        self.services = services
        self.config = config
        self.logger = logger
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Display user statistics"""
        try:
            user_service = self.services['user_service']
            user = await user_service.get_or_create_user(update.effective_user)
            
            # Handle both database and in-memory users
            if isinstance(user, dict):
                # In-memory user
                level = user['level']
                experience = user['experience_points']
                messages_count = user['messages_count']
                hubcoins = user['hubcoins']
                reputation = user['reputation']
                daily_streak = user['daily_streak'] or 0
                vip_member = user['vip_member']
                join_date = user['join_date']
                achievements = user.get('achievements', [])
                prestige = user['prestige']
                first_name = user['first_name']
            else:
                # Database user
                level = user.level
                experience = user.experience_points
                messages_count = user.messages_count
                hubcoins = user.hubcoins
                reputation = user.reputation
                daily_streak = user.daily_streak or 0
                vip_member = user.vip_member
                join_date = user.join_date
                achievements = user.achievements or []
                prestige = user.prestige
                first_name = user.first_name
            
            # Calculate progress
            next_level_exp = (level + 1) ** 2 * 50
            current_level_exp = level ** 2 * 50
            progress = ((experience - current_level_exp) / (next_level_exp - current_level_exp) * 100)
            progress = max(0, min(100, progress))
            
            # Create progress bar
            filled = int(progress / 5)
            progress_bar = "█" * filled + "░" * (20 - filled)
            
            # Build stats message
            stats_text = f"""
📊 **{first_name}'s Statistics** 📊

**Level Progress**
├ Level: {level} {'🌟' * prestige}
├ Experience: {experience:,} XP
├ Progress: {progress:.1f}%
└ [{progress_bar}]

**Activity Stats**
├ Messages: {messages_count:,}
├ Daily Streak: {daily_streak} 🔥
└ Member Since: {join_date.strftime('%B %d, %Y')}

**Economy**
├ HubCoins: {hubcoins:,} 💰
├ Reputation: {reputation} 👍
└ VIP Status: {'✅ Active' if vip_member else '❌ Inactive'}

**Achievements**
└ Unlocked: {len(achievements)} 🏆
"""
            
            # Send message
            msg = await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Schedule deletion
            if self.config.message_delete_delay > 0:
                asyncio.create_task(
                    self._delete_message_after_delay(
                        context.bot,
                        update.effective_chat.id,
                        msg.message_id
                    )
                )
            
        except Exception as e:
            self.logger.error(f"Error in stats command: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ An error occurred while fetching your stats. Please try again later."
            )
    
    async def _delete_message_after_delay(self, bot, chat_id: int, message_id: int) -> None:
        """Delete message after configured delay"""
        await asyncio.sleep(self.config.message_delete_delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except (BadRequest, TelegramError) as e:
            self.logger.debug(f"Could not delete message {message_id}: {e}")

# ==================== Main Bot Application ====================

class LevelUpBot:
    """Main bot application with resilient architecture"""
    
    def __init__(self):
        try:
            self.config = BotConfig.from_env()
            self.logger = BotLogger.setup(self.config)
            self.logger.info(f"Starting LevelUp Leo Bot in {self.config.environment} mode")
            
            # Initialize database manager
            self.db_manager = DatabaseManager(self.config, self.logger)
            
            # Initialize services
            self._initialize_services()
            
            # Initialize handlers
            self._initialize_handlers()
            
            self.logger.info("Bot initialization complete")
            
        except Exception as e:
            logging.critical(f"Failed to initialize bot: {e}", exc_info=True)
            raise
    
    def _initialize_services(self) -> None:
        """Initialize all services"""
        self.services = {
            'user_service': UserService(self.db_manager, self.logger),
        }
        
        # Only initialize AI service if API key is provided
        if self.config.gemini_api_key and self.config.gemini_api_key != 'dummy_key':
            try:
                genai.configure(api_key=self.config.gemini_api_key)
                self.logger.info("AI service initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize AI service: {e}")
    
    def _initialize_handlers(self) -> None:
        """Initialize command handlers"""
        self.handlers = {
            'stats': StatsCommandHandler(self.services, self.config, self.logger),
        }
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular messages for leveling"""
        try:
            if not update.message or not update.effective_user:
                return
            
            # Check if message is from the configured group
            if self.config.group_id and update.effective_chat.id != self.config.group_id:
                return
            
            user_service = self.services['user_service']
            
            # Get or create user
            user = await user_service.get_or_create_user(update.effective_user)
            
            # Update activity and check for level up
            new_level = await user_service.update_user_activity(update.effective_user.id)
            
            if new_level:
                # Send level up message
                username = update.effective_user.username or update.effective_user.first_name
                level_up_msg = f"🎉 Congratulations @{username}! You've reached Level {new_level}! 🚀"
                
                msg = await update.message.reply_text(level_up_msg)
                
                # Schedule deletion
                if self.config.message_delete_delay > 0:
                    asyncio.create_task(
                        self._delete_message_after_delay(
                            context.bot,
                            update.effective_chat.id,
                            msg.message_id
                        )
                    )
        
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def _delete_message_after_delay(self, bot, chat_id: int, message_id: int) -> None:
        """Delete message after delay"""
        await asyncio.sleep(self.config.message_delete_delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            self.logger.debug(f"Could not delete message: {e}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot"""
        self.logger.error(f"Exception while handling update: {context.error}", exc_info=True)
    
    async def run(self) -> None:
        """Run the bot application"""
        # Create Telegram application
        application = (
            Application.builder()
            .token(self.config.bot_token)
            .pool_timeout(30)
            .connect_timeout(30)
            .read_timeout(30)
            .build()
        )
        
        # Add error handler
        application.add_error_handler(self.error_handler)
        
        # Add command handlers
        application.add_handler(
            CommandHandler("stats", self.handlers['stats'].handle)
        )
        
        # Add message handler for leveling
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Start health check server
        asyncio.create_task(self._start_health_server())
        
        # Start the bot
        self.logger.info("Starting bot polling...")
        await application.run_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True
        )
    
    async def _start_health_server(self) -> None:
        """Start health check web server"""
        app = web.Application()
        app.router.add_get('/', self._health_check)
        app.router.add_get('/health', self._health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.config.port)
        await site.start()
        
        self.logger.info(f"Health check server started on port {self.config.port}")
    
    async def _health_check(self, request) -> web.Response:
        """Health check endpoint"""
        status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'connected' if not self.db_manager.use_memory else 'in-memory',
            'environment': self.config.environment
        }
        return web.Response(
            text=json.dumps(status),
            content_type='application/json'
        )

# ==================== Entry Point ====================

def main():
    """Main entry point"""
    try:
        bot = LevelUpBot()
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.critical(f"Critical error: {e}", exc_info=True)
        raise

import asyncio

if __name__ == "__main__":
    logging.info("Starting LevelUp Leo Bot in production mode")

    bot = LevelUpBot()
    asyncio.run(bot.run())
