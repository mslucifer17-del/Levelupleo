# UPDATED BOT.PY WITH BETTER LOGGING

import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import Database
from level_system import LevelSystem
from economy import EconomySystem
from gemini_handler import GeminiHandler
import config

# Set up detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class LevelupLeoBot:
    def __init__(self):
        self.db = Database()
        self.level_system = LevelSystem()
        self.economy = EconomySystem(self.db)
        self.gemini = GeminiHandler()
        
        self.level_stickers = {
            1: "CAACAgIAAxkBAAEBaZJlwqXzAAF",
            5: "CAACAgIAAxkBAAEBaZJlwqXzAAG", 
            10: "CAACAgIAAxkBAAEBaZJlwqXzAAH",
            25: "CAACAgIAAxkBAAEBaZJlwqXzAAI",
        }
        
        self.special_ranks = {
            100: "🎖️ Pro Promoter",
            110: "🌟 Promotion Guru", 
            125: "👑 The Legend",
        }

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        chat = update.effective_chat
        chat_type = chat.type
        
        logger.info(f"Start command from user {user.id} in {chat_type} chat {chat.id}")
        
        # Add user to database
        await self.db.add_user(user.id, user.first_name, chat.id, user.username)
        
        welcome_text = (
            f"🎉 Welcome to **Levelup Leo Bot**! 🎉\n\n"
            f"Hey {user.first_name}! I'm Leo, your level-up companion! 🦁\n\n"
            f"📊 Commands:\n"
            f"/level - Check your level\n"
            f"/top - Leaderboard\n"
            f"/shop - HubCoins shop\n"
            f"/balance - Check coins\n"
            f"/help - All commands\n\n"
            f"💪 Chat to earn XP and level up!"
        )
        
        # Test message to verify bot can send messages
        try:
            await update.message.reply_text(welcome_text, parse_mode='Markdown')
            logger.info(f"Successfully sent welcome message to user {user.id}")
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process all messages for XP"""
        if not update.message or not update.message.text:
            return
            
        user = update.effective_user
        chat = update.effective_chat
        
        # Skip bots
        if user.is_bot:
            return
            
        user_id = user.id
        user_name = user.first_name
        chat_id = chat.id
        
        logger.info(f"Message from {user_name} ({user_id}) in chat {chat_id}: {update.message.text[:50]}...")
        
        # Check cooldown
        last_message_time = await self.db.get_last_message_time(user_id, chat_id)
        current_time = datetime.now()
        
        if last_message_time and (current_time - last_message_time < timedelta(seconds=60)):
            logger.debug(f"Cooldown active for user {user_id}")
            return
        
        # Process XP
        try:
            xp_gained = random.randint(10, 30)
            user_data = await self.db.get_user(user_id, chat_id)
            
            if not user_data:
                await self.db.add_user(user_id, user_name, chat_id, user.username)
                user_data = await self.db.get_user(user_id, chat_id)
                logger.info(f"Added new user {user_name} to database")
            
            old_level = user_data['level']
            new_xp = user_data['xp'] + xp_gained
            new_level = self.level_system.calculate_level(new_xp)
            
            # Add coins
            coins_earned = random.randint(1, 5)
            await self.economy.add_coins(user_id, chat_id, coins_earned)
            
            # Update database
            await self.db.update_xp(user_id, chat_id, new_xp, new_level)
            await self.db.update_last_message_time(user_id, chat_id)
            
            logger.info(f"User {user_name} gained {xp_gained} XP (Total: {new_xp}, Level: {new_level})")
            
            # Level up handling
            if new_level > old_level:
                await self.handle_level_up(update, context, user_id, user_name, old_level, new_level, chat_id)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def handle_level_up(self, update, context, user_id, user_name, old_level, new_level, chat_id):
        """Handle level up notifications"""
        try:
            level_message = f"🎉 {user_name} leveled up to Level {new_level}! 🚀"
            
            # Send level up message
            await context.bot.send_message(
                chat_id=chat_id, 
                text=level_message, 
                parse_mode='Markdown'
            )
            logger.info(f"Sent level up message for {user_name} to level {new_level}")
            
        except Exception as e:
            logger.error(f"Error sending level up message: {e}")

    async def level_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Level command"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        logger.info(f"Level command from user {user_id}")
        
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data:
            await update.message.reply_text("Start chatting to earn XP! 💬")
            return
        
        level, xp = user_data['level'], user_data['xp']
        
        level_text = (
            f"📊 **{update.effective_user.first_name}'s Stats**\n\n"
            f"🎯 Level: **{level}**\n"
            f"✨ Total XP: **{xp}**\n"
            f"💪 Keep chatting to level up!"
        )
        await update.message.reply_text(level_text, parse_mode='Markdown')

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test command to check if bot is working"""
        user = update.effective_user
        chat = update.effective_chat
        
        test_message = (
            f"🤖 **Bot Test** 🤖\n\n"
            f"✅ Bot is working!\n"
            f"👤 User: {user.first_name}\n"
            f"💬 Chat: {chat.title if chat.title else 'Private'}\n"
            f"🆔 Chat ID: {chat.id}\n"
            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await update.message.reply_text(test_message, parse_mode='Markdown')
        logger.info(f"Test command executed by {user.id}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        help_text = (
            "🦁 **Levelup Leo Bot - Help** 🦁\n\n"
            "📊 **Commands:**\n"
            "/start - Start the bot\n"
            "/level - Check your level\n" 
            "/top - Leaderboard\n"
            "/balance - Check coins\n"
            "/test - Test if bot is working\n"
            "/help - This message\n\n"
            "💡 **How it works:**\n"
            "• Send messages to earn XP\n"
            "• Level up automatically\n"
            "• Earn coins for leveling up\n"
            "• Compete on leaderboard!\n\n"
            "Happy Leveling! 🚀"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

async def initialize_bot():
    """Initialize the bot with database"""
    logger.info("Initializing Levelup Leo Bot...")
    
    # Initialize database
    db = Database()
    await db.create_pool()
    await db.setup_tables()
    logger.info("Database initialized successfully!")
    
    # Create bot instance
    bot = LevelupLeoBot()
    bot.db = db
    bot.economy = EconomySystem(db)
    
    return bot

def main():
    """Main function"""
    logger.info("Starting Levelup Leo Bot...")
    
    try:
        # Create new event loop for Render
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Initialize bot
        bot = loop.run_until_complete(initialize_bot())
        
        # Create application
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("level", bot.level_command))
        application.add_handler(CommandHandler("test", bot.test_command))
        application.add_handler(CommandHandler("help", bot.help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
        
        logger.info("Bot setup complete. Starting polling...")
        
        # Start polling
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
