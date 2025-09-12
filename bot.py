import os
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai
from telegram import Update, Sticker, ChatMember, Chat
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, 
    ChatMemberHandler, filters
)
from telegram.constants import ParseMode
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()
engine = create_engine(os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db'))
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    level = Column(Integer, default=0)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0)
    hubcoins = Column(Integer, default=0)
    last_message_date = Column(DateTime)
    vip_member = Column(Boolean, default=False)
    custom_title = Column(String, default="")

# Create tables
Base.metadata.create_all(engine)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GROUP_ID = int(os.environ.get('GROUP_ID', 0))  # Your group ID

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-pro')

# Sticker IDs for different levels (replace with your actual sticker IDs)
LEVEL_STICKERS = {
    1: "CAACAgIAAxkBAAEL...",  # Sticker for level 1
    5: "CAACAgIAAxkBAAEL...",  # Sticker for level 5
    10: "CAACAgIAAxkBAAEL...", # Sticker for level 10
    25: "CAACAgIAAxkBAAEL...", # Sticker for level 25
    50: "CAACAgIAAxkBAAEL...", # Sticker for level 50
    100: "CAACAgIAAxkBAAEL...", # Sticker for level 100
}

# Level requirements - progressive system
def get_level_requirements(level: int) -> int:
    if level <= 10:
        return level * 10
    elif level <= 25:
        return 100 + (level - 10) * 25
    elif level <= 50:
        return 475 + (level - 25) * 50
    else:
        return 1725 + (level - 50) * 100

# Calculate current level based on message count
def calculate_level(message_count: int) -> Tuple[int, int]:
    level = 0
    while message_count >= get_level_requirements(level + 1):
        level += 1
    return level, get_level_requirements(level + 1) - message_count

# Generate level up message using Gemini
async def generate_level_up_message(level: int, username: str) -> str:
    prompt = f"Write a short, funny, and motivating message in Hinglish for a user {username} who just reached Level {level} in a promotion group. Mention the level number and keep it under 200 characters."
    
    try:
        response = await gemini_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error generating Gemini message: {e}")
        return f"Congratulations {username}! You've reached level {level}! 🎉"

# Welcome message for new users
async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"Hey {user.first_name}, welcome to ThePromotionHub! "
        f"Hmm, tumhari level to 0 hai. Message karo or apni level up karo 💪."
    )
    
    await update.message.reply_text(welcome_text)
    
    # Add user to database
    session = Session()
    try:
        if not session.query(User).filter(User.user_id == user.id).first():
            new_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                level=0,
                messages_count=0,
                hubcoins=10  # Starting bonus
            )
            session.add(new_user)
            session.commit()
    except Exception as e:
        logger.error(f"Error adding user to database: {e}")
    finally:
        session.close()

# Handle messages and update levels
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return
        
    user = update.effective_user
    session = Session()
    
    try:
        # Get or create user
        db_user = session.query(User).filter(User.user_id == user.id).first()
        if not db_user:
            db_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                level=0,
                messages_count=0,
                hubcoins=10
            )
            session.add(db_user)
        
        # Update message count
        db_user.messages_count += 1
        db_user.last_message_date = datetime.now()
        
        # Award HubCoins (1-3 per message)
        db_user.hubcoins += random.randint(1, 3)
        
        # Check for level up
        old_level = db_user.level
        new_level, remaining = calculate_level(db_user.messages_count)
        
        if new_level > old_level:
            db_user.level = new_level
            
            # Send level up message
            level_up_text = await generate_level_up_message(new_level, user.first_name)
            await update.message.reply_text(level_up_text)
            
            # Send sticker if available for this level
            if new_level in LEVEL_STICKERS:
                await update.message.reply_sticker(LEVEL_STICKERS[new_level])
            
            # Check for prestige eligibility
            if new_level >= 100 and not db_user.prestige:
                prestige_text = (
                    f"🎉 Amazing {user.first_name}! You've reached Level 100! 🎉\n\n"
                    f"Would you like to prestige and start over with special benefits? "
                    f"Use /prestige to reset to Level 1 with a prestige badge! 🌟"
                )
                await update.message.reply_text(prestige_text)
            
            # Award bonus HubCoins for leveling up
            db_user.hubcoins += new_level * 5
        
        session.commit()
        
        # Occasionally show progress
        if random.random() < 0.05:  # 5% chance
            progress_text = (
                f"{user.first_name}, you're at Level {db_user.level} "
                f"with {db_user.messages_count} messages. "
                f"Next level in {remaining} messages! 💪"
            )
            await update.message.reply_text(progress_text)
            
    except Exception as e:
        logger.error(f"Error updating user: {e}")
    finally:
        session.close()

# Prestige command
async def prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    session = Session()
    
    try:
        db_user = session.query(User).filter(User.user_id == user.id).first()
        if not db_user:
            await update.message.reply_text("You need to send some messages first!")
            return
            
        if db_user.level < 100:
            await update.message.reply_text("You need to reach Level 100 before you can prestige!")
            return
            
        if db_user.prestige > 0:
            await update.message.reply_text(f"You already have {db_user.prestige} prestige levels! 🌟")
            return
            
        # Reset level but increase prestige
        db_user.prestige += 1
        db_user.level = 1
        db_user.messages_count = 0
        
        # Award bonus HubCoins for prestiging
        db_user.hubcoins += 500
        
        session.commit()
        
        prestige_text = (
            f"🎊 Congratulations {user.first_name}! 🎊\n\n"
            f"You've prestiged and are now back at Level 1 with a prestige badge! 🌟\n"
            f"You've received 500 HubCoins as a bonus!\n\n"
            f"Your dedication is impressive! Keep leveling up!"
        )
        
        await update.message.reply_text(prestige_text)
        
    except Exception as e:
        logger.error(f"Error processing prestige: {e}")
    finally:
        session.close()

# Shop command
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    shop_text = (
        "🛒 Welcome to ThePromotionHub Shop! 🛒\n\n"
        "Here's what you can buy with your HubCoins:\n\n"
        "🌟 Spotlight Promotion - 500 Coins\n"
        "   Get your content featured in the group spotlight\n\n"
        "🎖️ Custom Title - 1000 Coins\n"
        "   Get a custom title next to your name for a week\n\n"
        "💎 VIP Access - 5000 Coins\n"
        "   Get access to exclusive VIP features\n\n"
        "Use /buy [item] to purchase something!\n"
        "Check your coins with /coins"
    )
    
    await update.message.reply_text(shop_text)

# Coins command
async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    session = Session()
    
    try:
        db_user = session.query(User).filter(User.user_id == user.id).first()
        if not db_user:
            await update.message.reply_text("You don't have any HubCoins yet. Start chatting to earn some!")
            return
            
        coins_text = (
            f"{user.first_name}, you have {db_user.hubcoins} HubCoins! 💰\n\n"
            f"Visit the shop with /shop to see what you can buy!"
        )
        
        await update.message.reply_text(coins_text)
        
    except Exception as e:
        logger.error(f"Error checking coins: {e}")
    finally:
        session.close()

# Spotlight feature
async def spotlight_feature(context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    
    try:
        # Find an active user from the last 7 days
        one_week_ago = datetime.now() - timedelta(days=7)
        active_users = session.query(User).filter(
            User.last_message_date >= one_week_ago
        ).all()
        
        if not active_users:
            return
            
        # Select a random active user
        selected_user = random.choice(active_users)
        
        # Get user info
        try:
            chat_member = await context.bot.get_chat_member(GROUP_ID, selected_user.user_id)
            username = f"@{chat_member.user.username}" if chat_member.user.username else chat_member.user.first_name
        except:
            username = selected_user.first_name
        
        # Create spotlight message
        spotlight_text = (
            f"🌟 Today's Spotlight Member is {username}! 🌟\n\n"
            f"This active member is Level {selected_user.level} "
            f"with {selected_user.prestige} prestige levels!\n\n"
            f"Let's all give them some support and check out their content!\n\n"
            f"Want to be in the spotlight? Stay active in the group!"
        )
        
        # Send spotlight message
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=spotlight_text,
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error with spotlight feature: {e}")
    finally:
        session.close()

# Stats command
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    session = Session()
    
    try:
        db_user = session.query(User).filter(User.user_id == user.id).first()
        if not db_user:
            await update.message.reply_text("You haven't started your journey yet! Send a message to begin.")
            return
            
        next_level_req = get_level_requirements(db_user.level + 1)
        progress = min(100, int((db_user.messages_count / next_level_req) * 100)) if next_level_req > 0 else 100
        
        stats_text = (
            f"📊 {user.first_name}'s Stats:\n\n"
            f"• Level: {db_user.level} {'🌟' * db_user.prestige}\n"
            f"• Messages: {db_user.messages_count}\n"
            f"• HubCoins: {db_user.hubcoins} 💰\n"
            f"• Progress to next level: {progress}%\n"
            f"• VIP Status: {'Yes 🎖️' if db_user.vip_member else 'No'}\n"
        )
        
        if db_user.custom_title:
            stats_text += f"• Custom Title: {db_user.custom_title}\n"
        
        await update.message.reply_text(stats_text)
        
    except Exception as e:
        logger.error(f"Error with stats command: {e}")
    finally:
        session.close()

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# Main function
def main() -> None:
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", send_welcome_message))
    application.add_handler(CommandHandler("prestige", prestige_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("coins", coins_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Handle all text messages except commands
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Job queue for periodic tasks (like spotlight)
    job_queue = application.job_queue
    job_queue.run_repeating(spotlight_feature, interval=timedelta(hours=24), first=10)
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
