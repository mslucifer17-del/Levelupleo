"""
LevelUp Leo Bot - Professional Edition
A comprehensive Telegram leveling and economy bot with modern architecture
"""

import os
import json
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
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
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, 
    func, BigInteger, text, Float, JSON, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session as SQLSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool, QueuePool

# ==================== Configuration ====================

@dataclass
class BotConfig:
    """Bot configuration with validation"""
    bot_token: str
    gemini_api_key: str
    database_url: str
    group_id: int
    port: int
    environment: str = "production"
    log_level: str = "INFO"
    max_retries: int = 5
    retry_delay: int = 5
    message_delete_delay: int = 60
    spotlight_interval_hours: int = 24
    cleanup_interval_hours: int = 6
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Create config from environment variables"""
        required_vars = ["BOT_TOKEN", "GEMINI_API_KEY", "GROUP_ID"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return cls(
            bot_token=os.environ["BOT_TOKEN"],
            gemini_api_key=os.environ["GEMINI_API_KEY"],
            database_url=os.environ.get("DATABASE_URL", "sqlite:///levelup_bot.db"),
            group_id=int(os.environ["GROUP_ID"]),
            port=int(os.environ.get("PORT", 8443)),
            environment=os.environ.get("ENVIRONMENT", "production"),
            log_level=os.environ.get("LOG_LEVEL", "INFO")
        )

# ==================== Logging Setup ====================

class BotLogger:
    """Centralized logging configuration"""
    
    @staticmethod
    def setup(config: BotConfig) -> logging.Logger:
        """Setup structured logging"""
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
    """Enhanced user model with indexes and constraints"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255), nullable=False)
    
    # Leveling System
    level = Column(Integer, default=0, index=True)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0, index=True)
    experience_points = Column(Integer, default=0)
    
    # Economy
    hubcoins = Column(Integer, default=10)
    reputation = Column(Integer, default=0)
    
    # Activity Tracking
    last_message_date = Column(DateTime, index=True)
    join_date = Column(DateTime, default=datetime.utcnow)
    daily_streak = Column(Integer, default=0)
    last_daily_date = Column(DateTime)
    
    # Premium Features
    vip_member = Column(Boolean, default=False, index=True)
    custom_title = Column(String(50), default="")
    custom_title_expiry = Column(DateTime)
    spotlight_priority = Column(Boolean, default=False)
    
    # Achievements and Stats
    achievements = Column(JSON, default=list)
    stats = Column(JSON, default=dict)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_user_activity', 'last_message_date', 'level'),
        Index('idx_user_economy', 'hubcoins', 'reputation'),
    )
    
    def get_display_name(self) -> str:
        """Get formatted display name with badges"""
        title = f" [{self.custom_title}]" if self.custom_title else ""
        prestige_badge = '🌟' * self.prestige if self.prestige > 0 else ''
        vip_badge = ' 👑' if self.vip_member else ''
        return f"{self.first_name}{title}{prestige_badge}{vip_badge}"

# ==================== Database Manager ====================

class DatabaseManager:
    """Professional database connection manager"""
    
    def __init__(self, config: BotConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.engine = None
        self.session_factory = None
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Initialize database with retry logic and connection pooling"""
        for attempt in range(self.config.max_retries):
            try:
                # Configure connection pool based on database type
                if self.config.database_url.startswith('postgresql'):
                    pool_class = QueuePool
                    pool_args = {
                        'pool_size': 10,
                        'max_overflow': 20,
                        'pool_timeout': 30,
                        'pool_recycle': 1800,
                    }
                    connect_args = {'connect_timeout': 30}
                else:
                    pool_class = NullPool
                    pool_args = {}
                    connect_args = {}
                
                self.engine = create_engine(
                    self.config.database_url,
                    poolclass=pool_class,
                    connect_args=connect_args,
                    **pool_args
                )
                
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                # Create session factory
                self.session_factory = sessionmaker(bind=self.engine)
                
                # Create tables
                Base.metadata.create_all(self.engine)
                
                self.logger.info("Database initialized successfully")
                return
                
            except SQLAlchemyError as e:
                self.logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    asyncio.sleep(delay)
                else:
                    raise RuntimeError("Failed to initialize database after maximum retries")
    
    @asynccontextmanager
    async def get_session(self):
        """Async context manager for database sessions"""
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

# ==================== Service Layer ====================

class UserService:
    """Business logic for user operations"""
    
    def __init__(self, db_manager: DatabaseManager, logger: logging.Logger):
        self.db = db_manager
        self.logger = logger
    
    async def get_or_create_user(self, user_data) -> UserModel:
        """Get or create user with proper error handling"""
        async with self.db.get_session() as session:
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
        async with self.db.get_session() as session:
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
        """Calculate level based on experience using a logarithmic formula"""
        import math
        if experience <= 0:
            return 0
        return int(math.sqrt(experience / 50))

# ==================== Achievement System ====================

class AchievementType(Enum):
    """Achievement types enumeration"""
    FIRST_MESSAGE = "first_message"
    LEVEL_10 = "level_10"
    LEVEL_50 = "level_50"
    LEVEL_100 = "level_100"
    VIP_MEMBER = "vip_member"
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    RICH = "rich_10k"

@dataclass
class Achievement:
    """Achievement data class"""
    id: str
    name: str
    description: str
    reward: int
    icon: str
    
class AchievementService:
    """Service for managing achievements"""
    
    ACHIEVEMENTS = {
        AchievementType.FIRST_MESSAGE: Achievement(
            "first_message", "First Words", "Send your first message", 50, "🎯"
        ),
        AchievementType.LEVEL_10: Achievement(
            "level_10", "Rising Star", "Reach level 10", 100, "⭐"
        ),
        AchievementType.LEVEL_50: Achievement(
            "level_50", "Half Century", "Reach level 50", 500, "🏆"
        ),
        AchievementType.LEVEL_100: Achievement(
            "level_100", "Centurion", "Reach level 100", 1000, "👑"
        ),
        AchievementType.VIP_MEMBER: Achievement(
            "vip_member", "Elite Member", "Purchase VIP status", 200, "💎"
        ),
        AchievementType.STREAK_7: Achievement(
            "streak_7", "Consistent", "7-day message streak", 150, "🔥"
        ),
        AchievementType.STREAK_30: Achievement(
            "streak_30", "Dedicated", "30-day message streak", 500, "💫"
        ),
        AchievementType.RICH: Achievement(
            "rich_10k", "Wealthy", "Accumulate 10,000 coins", 1000, "💰"
        ),
    }
    
    def __init__(self, db_manager: DatabaseManager, logger: logging.Logger):
        self.db = db_manager
        self.logger = logger
    
    async def check_and_award(
        self, user_id: int, achievement_type: AchievementType
    ) -> Optional[Achievement]:
        """Check and award achievement if not already earned"""
        achievement = self.ACHIEVEMENTS.get(achievement_type)
        if not achievement:
            return None
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(UserModel).filter(UserModel.user_id == user_id).first
            )
            
            if not user:
                return None
            
            # Check if already earned
            if not user.achievements:
                user.achievements = []
            
            if achievement.id in user.achievements:
                return None
            
            # Award achievement
            user.achievements.append(achievement.id)
            user.hubcoins += achievement.reward
            
            # Update stats
            if not user.stats:
                user.stats = {}
            user.stats['total_achievements'] = len(user.achievements)
            
            await asyncio.to_thread(session.commit)
            self.logger.info(f"User {user_id} earned achievement: {achievement.name}")
            
            return achievement

# ==================== Command Handlers ====================

class CommandHandler(ABC):
    """Abstract base class for command handlers"""
    
    def __init__(self, services: Dict[str, Any], config: BotConfig, logger: logging.Logger):
        self.services = services
        self.config = config
        self.logger = logger
    
    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the command"""
        pass

class StatsCommandHandler(CommandHandler):
    """Handler for /stats command"""
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Display user statistics"""
        try:
            user_service = self.services['user_service']
            user = await user_service.get_or_create_user(update.effective_user)
            
            # Calculate progress
            next_level_exp = (user.level + 1) ** 2 * 50
            current_level_exp = user.level ** 2 * 50
            progress = (
                (user.experience_points - current_level_exp) / 
                (next_level_exp - current_level_exp) * 100
            )
            progress = max(0, min(100, progress))
            
            # Create progress bar
            filled = int(progress / 5)
            progress_bar = "█" * filled + "░" * (20 - filled)
            
            # Build stats message
            stats_text = f"""
📊 **{user.get_display_name()}'s Statistics** 📊

**Level Progress**
├ Level: {user.level} {'🌟' * user.prestige}
├ Experience: {user.experience_points:,} XP
├ Progress: {progress:.1f}%
└ [{progress_bar}]

**Activity Stats**
├ Messages: {user.messages_count:,}
├ Daily Streak: {user.daily_streak or 0} 🔥
└ Member Since: {user.join_date.strftime('%B %d, %Y')}

**Economy**
├ HubCoins: {user.hubcoins:,} 💰
├ Reputation: {user.reputation} 👍
└ VIP Status: {'✅ Active' if user.vip_member else '❌ Inactive'}

**Achievements**
└ Unlocked: {len(user.achievements or [])} 🏆
"""
            
            # Create inline keyboard
            keyboard = [
                [
                    InlineKeyboardButton("🏆 Achievements", callback_data='achievements'),
                    InlineKeyboardButton("📈 Leaderboard", callback_data='leaderboard')
                ],
                [InlineKeyboardButton("« Back", callback_data='main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            msg = await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # Schedule message deletion
            asyncio.create_task(
                self._delete_message_after_delay(
                    context.bot,
                    update.effective_chat.id,
                    msg.message_id
                )
            )
            
        except Exception as e:
            self.logger.error(f"Error in stats command: {e}")
            await update.message.reply_text(
                "❌ An error occurred. Please try again later."
            )
    
    async def _delete_message_after_delay(self, bot, chat_id: int, message_id: int) -> None:
        """Delete message after configured delay"""
        await asyncio.sleep(self.config.message_delete_delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except (BadRequest, TelegramError) as e:
            self.logger.warning(f"Could not delete message {message_id}: {e}")

# ==================== Shop System ====================

@dataclass
class ShopItem:
    """Shop item data class"""
    id: str
    name: str
    description: str
    price: int
    icon: str
    category: str
    duration_days: Optional[int] = None

class ShopService:
    """Service for managing the shop"""
    
    ITEMS = {
        'custom_title': ShopItem(
            'custom_title', 'Custom Title', 
            'Display a custom title for 7 days', 1000, '🎭', 'cosmetic', 7
        ),
        'spotlight': ShopItem(
            'spotlight', 'Spotlight Priority', 
            'Get priority in daily spotlight', 2500, '🌟', 'feature', None
        ),
        'vip_status': ShopItem(
            'vip_status', 'VIP Membership', 
            'Permanent VIP status with exclusive perks', 10000, '👑', 'premium', None
        ),
        'coin_boost': ShopItem(
            'coin_boost', 'Coin Boost', 
            'Double coins for 24 hours', 500, '💰', 'boost', 1
        ),
    }
    
    def __init__(self, db_manager: DatabaseManager, logger: logging.Logger):
        self.db = db_manager
        self.logger = logger
    
    async def purchase_item(self, user_id: int, item_id: str, **kwargs) -> Tuple[bool, str]:
        """Process item purchase"""
        item = self.ITEMS.get(item_id)
        if not item:
            return False, "Item not found in shop"
        
        async with self.db.get_session() as session:
            user = await asyncio.to_thread(
                session.query(UserModel).filter(UserModel.user_id == user_id).first
            )
            
            if not user:
                return False, "User not found"
            
            if user.hubcoins < item.price:
                return False, f"Insufficient coins. You need {item.price:,} coins."
            
            # Process purchase based on item type
            user.hubcoins -= item.price
            
            if item_id == 'custom_title':
                title = kwargs.get('title', 'VIP')[:20]
                user.custom_title = title
                user.custom_title_expiry = datetime.utcnow() + timedelta(days=item.duration_days)
                message = f"Custom title '{title}' activated for 7 days!"
            
            elif item_id == 'spotlight':
                user.spotlight_priority = True
                message = "Spotlight priority activated! You'll be featured soon."
            
            elif item_id == 'vip_status':
                user.vip_member = True
                message = "Welcome to VIP! Enjoy your exclusive perks."
            
            else:
                message = f"Purchased {item.name} successfully!"
            
            await asyncio.to_thread(session.commit)
            self.logger.info(f"User {user_id} purchased {item_id}")
            
            return True, message

# ==================== AI Service ====================

class AIService:
    """Service for AI-powered features"""
    
    def __init__(self, api_key: str, logger: logging.Logger):
        self.logger = logger
        self.model = None
        self._initialize_ai(api_key)
    
    def _initialize_ai(self, api_key: str) -> None:
        """Initialize Gemini AI"""
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.logger.info("AI service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize AI service: {e}")
            self.model = None
    
    async def generate_level_message(self, level: int, username: str) -> str:
        """Generate creative level-up message"""
        if not self.model:
            return self._get_fallback_message(level, username)
        
        prompt = (
            f"Create a very short, energetic congratulations message for {username} "
            f"who just reached Level {level}. Use emojis and be creative. "
            f"Maximum 2 sentences. Mix English with a bit of Hindi/Hinglish."
        )
        
        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config={'temperature': 0.9, 'max_output_tokens': 100}
            )
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"AI generation failed: {e}")
            return self._get_fallback_message(level, username)
    
    def _get_fallback_message(self, level: int, username: str) -> str:
        """Fallback messages when AI is unavailable"""
        messages = [
            f"🎉 Amazing {username}! Level {level} unlocked! Keep crushing it! 🚀",
            f"🔥 {username} just hit Level {level}! Absolute legend! 💪",
            f"⚡ Level {level} achieved! {username} is on fire! 🌟",
            f"🏆 Congratulations {username}! Level {level} conquered! 👑",
        ]
        return random.choice(messages)

# ==================== Main Bot Application ====================

class LevelUpBot:
    """Main bot application class"""
    
    def __init__(self):
        self.config = BotConfig.from_env()
        self.logger = BotLogger.setup(self.config)
        self.db_manager = DatabaseManager(self.config, self.logger)
        self._initialize_services()
        self._initialize_handlers()
    
    def _initialize_services(self) -> None:
        """Initialize all services"""
        self.services = {
            'user_service': UserService(self.db_manager, self.logger),
            'achievement_service': AchievementService(self.db_manager, self.logger),
            'shop_service': ShopService(self.db_manager, self.logger),
            'ai_service': AIService(self.config.gemini_api_key, self.logger),
        }
    
    def _initialize_handlers(self) -> None:
        """Initialize command handlers"""
        self.handlers = {
            'stats': StatsCommandHandler(self.services, self.config, self.logger),
        }
    
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
        
        # Register command handlers
        application.add_handler(
            CommandHandler("stats", self.handlers['stats'].handle)
        )
        
        # Start health check server
        asyncio.create_task(self._start_health_server())
        
        # Start the bot
        self.logger.info("Starting LevelUp Leo Bot...")
        await application.run_polling(
            poll_interval=1.0,
            timeout=30,
            drop_pending_updates=True
        )
    
    async def _start_health_server(self) -> None:
        """Start health check web server for deployment"""
        app = web.Application()
        app.router.add_get('/health', self._health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.config.port)
        await site.start()
        
        self.logger.info(f"Health check server started on port {self.config.port}")
    
    async def _health_check(self, request) -> web.Response:
        """Health check endpoint"""
        return web.Response(
            text=json.dumps({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat()
            }),
            content_type='application/json'
        )

# ==================== Entry Point ====================

def main():
    """Main entry point"""
    try:
        bot = LevelUpBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.critical(f"Critical error: {e}")
        raise

if __name__ == '__main__':
    main()
