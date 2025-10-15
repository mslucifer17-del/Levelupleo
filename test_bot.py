# FIXED BOT.PY - BOT WON'T RESPOND TO ITS OWN MESSAGES

import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleLevelupBot:
    def __init__(self):
        self.user_data = {}  # Simple in-memory storage for demo
        self.bot_id = None  # Will be set when bot starts
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        welcome_text = (
            f"🎉 Welcome to **Levelup Leo Bot**! 🎉\n\n"
            f"Hey {user.first_name}! I'm Leo, your level-up companion! 🦁\n\n"
            f"📊 Commands:\n"
            f"/level - Check your level\n"
            f"/top - Leaderboard\n"
            f"/help - All commands\n\n"
            f"💪 Start chatting to earn XP!"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
    async def level_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        
        # Initialize user data if not exists
        if user_id not in self.user_data:
            self.user_data[user_id] = {'xp': 0, 'level': 1, 'name': user_name}
        
        user_data = self.user_data[user_id]
        level_text = (
            f"📊 **{user_name}'s Stats**\n\n"
            f"🎯 Level: **{user_data['level']}**\n"
            f"✨ Total XP: **{user_data['xp']}**\n\n"
            f"Keep chatting to level up! 💪"
        )
        await update.message.reply_text(level_text, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # CRITICAL FIX: Ignore bot's own messages
        if update.effective_user.is_bot:
            return
            
        if not update.message or not update.message.text:
            return
            
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        
        # Skip if message is from bot itself
        if user_id == self.bot_id:
            return
        
        if user_id not in self.user_data:
            self.user_data[user_id] = {'xp': 0, 'level': 1, 'name': user_name}
        
        # Add random XP
        xp_gained = random.randint(10, 20)
        self.user_data[user_id]['xp'] += xp_gained
        
        # Simple level calculation
        new_level = self.user_data[user_id]['xp'] // 100 + 1
        old_level = self.user_data[user_id]['level']
        
        if new_level > old_level:
            self.user_data[user_id]['level'] = new_level
            level_msg = f"🎉 {user_name} leveled up to Level {new_level}! 🚀"
            await update.message.reply_text(level_msg)
    
    async def top_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.user_data:
            await update.message.reply_text("No users yet! Start chatting! 💬")
            return
        
        # Get top 10 users
        top_users = sorted(self.user_data.items(), 
                          key=lambda x: x[1]['xp'], 
                          reverse=True)[:10]
        
        leaderboard = "🏆 **TOP 10 LEADERBOARD** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id, data) in enumerate(top_users):
            position_icon = medals[i] if i < 3 else f"{i+1}."
            leaderboard += (
                f"{position_icon} **{data['name']}**\n"
                f"   Level {data['level']} • {data['xp']} XP\n\n"
            )
        
        await update.message.reply_text(leaderboard, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🦁 **Levelup Leo Bot - Help** 🦁\n\n"
            "📊 **Commands:**\n"
            "/start - Start the bot\n"
            "/level - Check your level\n"
            "/top - Leaderboard\n"
            "/help - This message\n\n"
            "💡 **How it works:**\n"
            "• Send messages to earn XP\n"
            "• Level up automatically\n"
            "• Compete on the leaderboard!\n\n"
            "Happy Leveling! 🚀"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def post_init(self, application: Application):
        """Get bot ID after initialization"""
        bot = await application.bot.get_me()
        self.bot_id = bot.id
        print(f"Bot ID set to: {self.bot_id}")

def main():
    """Simple main function"""
    print("Starting Simple Levelup Bot...")
    
    # Create bot
    bot = SimpleLevelupBot()
    
    # Build application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add post initialization handler
    application.post_init = bot.post_init
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("level", bot.level_command))
    application.add_handler(CommandHandler("top", bot.top_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    
    # IMPORTANT: Add filters to ignore bot messages and commands
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.User.is_bot, 
        bot.handle_message
    ))
    
    # Start bot
    print("Bot is now running and polling for updates...")
    application.run_polling()

if __name__ == '__main__':
    main()
