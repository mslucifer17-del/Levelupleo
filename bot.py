# -*- coding: utf-8 -*-

# LevelUp Leo Bot - Final Production Code for Web Service Hosting
# Includes a Flask web server to keep the service alive on Render.com

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
from sqlalchemy import BigInteger

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)  # ✅ This will store large Telegram IDs
    username = Column(String)
    first_name = Column(String, nullable=False)
    ...


# NEW: Imports for Flask Web Server
from flask import Flask
from threading import Thread

# --- Configuration ---
# 1. Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Environment Variables (IMPORTANT: Set these on your server)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///levelup_bot.db')
GROUP_ID = int(os.environ.get('GROUP_ID', 0))

if not all([BOT_TOKEN, GEMINI_API_KEY, GROUP_ID]):
    logger.critical("CRITICAL ERROR: BOT_TOKEN, GEMINI_API_KEY, or GROUP_ID is missing!")
    exit()

# 3. Database Setup (SQLAlchemy)
Base = declarative_base()
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String, nullable=False)
    
    level = Column(Integer, default=0)
    messages_count = Column(Integer, default=0)
    prestige = Column(Integer, default=0)
    hubcoins = Column(Integer, default=10) # Start with 10 coins
    reputation = Column(Integer, default=0)
    
    last_message_date = Column(DateTime)
    join_date = Column(DateTime, default=datetime.now)
    
    # Shop & Perks
    vip_member = Column(Boolean, default=False)
    custom_title = Column(String, default="")
    custom_title_expiry = Column(DateTime)
    spotlight_priority = Column(Boolean, default=False)
    
    def get_display_name(self):
        title = f" [{self.custom_title}]" if self.custom_title else ""
        prestige_badge = '🌟' * self.prestige if self.prestige > 0 else ''
        return f"{self.first_name}{title}{prestige_badge}"

Base.metadata.create_all(engine)

# 4. Gemini AI Initialization
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-pro')
except Exception as e:
    logger.error(f"Failed to configure Gemini AI: {e}")
    gemini_model = None

# 5. Sticker IDs (IMPORTANT: Replace these with your actual sticker file_ids)
LEVEL_STICKERS = {
    1: "CAACAgEAAxkBAAECZohow8nXm9oFdxnWioDIioN6859S4wACpQIAAkb-8Ec467BfJxQ8djYE", # Example: Hi
    5: "CAACAgIAAxkBAAECZnJow7hdgpqcTIT0DOLHNPGnzGRkKAAC2gcAAkb7rAQzJBAGerWb9DYE", # Example: Good
    10: "CAACAgIAAxkBAAECZnZow7kwKCGQatfYcbleyHa3PXnwTwAC_wADVp29Ctqt-n3kvEAkNgQ",# Example: Wow
    25: "CAACAgEAAxkBAAECZnhow7mGUl7Z1snxJyRNWP5037ziowACNwIAAh8GKEfvyfXEdjV49DYE",# Example: Awesome
    50: "CAACAgIAAxkBAAECZnpow7nEKLWwj_mqpOfukS5QgeEJRAACjQAD9wLIDySOeTFwpasYNgQ", # Example: Pro
    100: "CAACAgIAAxkBAAECZoZow8lb7GLHDtfqCdG5JFkAAb3tRq0AAvYSAAIp_UhJZrzas7gxByo2BA",# Example: Legend
}

# NEW: Flask Web Server setup
app = Flask(__name__)

@app.route('/')
def home():
    # This route will respond to Render's health checks
    return "Bot is running!"

def run_flask():
    # Render provides the PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# --- Core Bot Logic ---

# 1. Helper Functions
def get_level_requirements(level: int) -> int:
    """Calculates total messages needed for a certain level using a progressive formula."""
    if level <= 10: return level * 10
    elif level <= 25: return 100 + (level - 10) * 25
    elif level <= 50: return 475 + (level - 25) * 50
    else: return 1725 + (level - 50) * 100

def get_or_create_user(session, user_data: Update.effective_user) -> User:
    """Gets a user from the DB or creates a new one."""
    db_user = session.query(User).filter(User.user_id == user_data.id).first()
    if not db_user:
        db_user = User(
            user_id=user_data.id,
            username=user_data.username,
            first_name=user_data.first_name or "User",
        )
        session.add(db_user)
        session.commit()
    return db_user

async def generate_level_up_message(level: int, username: str) -> str:
    """Generates a unique level-up message using Gemini AI."""
    if not gemini_model:
        return f"Woooah {username}! Aap Level {level} par pahunch gaye! Keep it up! 🔥"
        
    prompt = f"Write a very short, cool, and motivating message in Hinglish for a user named '{username}' who just reached Level {level} in a Telegram group. Mention the level. Be creative and fun."
    try:
        response = await gemini_model.generate_content_async(prompt, safety_settings={'HARASSMENT':'block_none'})
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return f"Woooah {username}! Aap Level {level} par pahunch gaye! Keep it up! 🔥"

# 2. Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Namaste! Main LevelUp Leo hoon. Group mein message karke apni level badhao! /help se saare commands dekho.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📜 **LevelUp Leo Commands** 📜\n\n"
        "`/stats` - Apni level, coins aur progress dekho.\n"
        "`/coins` - Apne HubCoins ka balance dekho.\n"
        "`/shop` - Dekho ki tum HubCoins se kya khareed sakte ho.\n"
        "`/buy [item]` - Shop se kuch khareedo (e.g., `/buy title`)\n"
        "`/prestige` - Level 100 ke baad special badge ke liye level reset karo.\n"
        "Reply to a message with `/rep` to give reputation to a user."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        req_for_next = get_level_requirements(db_user.level + 1)
        messages_for_next = req_for_next - db_user.messages_count
        
        stats_text = (
            f"📊 **{db_user.get_display_name()}'s Stats**\n\n"
            f"• **Level:** {db_user.level}\n"
            f"• **Messages:** {db_user.messages_count}\n"
            f"• **HubCoins:** {db_user.hubcoins} 💰\n"
            f"• **Reputation:** {db_user.reputation} 👍\n"
            f"• **Next Level:** in {messages_for_next} messages.\n"
            f"• **VIP Status:** {'Yes 🎖️' if db_user.vip_member else 'No'}"
        )
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    finally:
        session.close()

async def prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        if db_user.level < 100:
            await update.message.reply_text("Prestige ke liye Level 100 tak pahunchna zaroori hai!")
            return

        db_user.prestige += 1
        db_user.level = 1
        db_user.messages_count = 0
        db_user.hubcoins += 500 * db_user.prestige # More coins for higher prestige
        session.commit()

        prestige_badge = '🌟' * db_user.prestige
        await update.message.reply_text(
            f"🎊 CONGRATULATIONS, {db_user.first_name}! 🎊\n\n"
            f"Aapne Prestige {db_user.prestige} haasil kar liya hai! {prestige_badge}\n"
            f"Aapki level reset ho gayi hai, aur aapko {500 * db_user.prestige} HubCoins ka bonus mila hai. Keep rocking!"
        )
    finally:
        session.close()

# 3. Message and Member Handlers
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        session = Session()
        try:
            get_or_create_user(session, member) # User ko DB mein add karein
            welcome_text = (
                f"Hey {member.first_name}, welcome to ThePromotionHub! 🎉\n\n"
                f"Right now your level is 0. Start messaging and grow your level 🚀."
            )
            await update.message.reply_text(welcome_text)

            # --- YEH HAI SABSE ZAROORI BADLAV ---
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
        
        # Level Up Check
        old_level = db_user.level
        new_level = 0
        while db_user.messages_count >= get_level_requirements(new_level + 1):
            new_level += 1
        
        if new_level > old_level:
            db_user.level = new_level
            db_user.hubcoins += new_level * 10 # Bonus coins on level up
            
            # Send Gemini message
            level_up_text = await generate_level_up_message(new_level, db_user.first_name)
            await update.message.reply_text(level_up_text)
            
            # Send Sticker
            if new_level in LEVEL_STICKERS:
                await update.message.reply_sticker(LEVEL_STICKERS[new_level])
            
            # Prestige Prompt at Level 100
            if new_level == 100:
                await update.message.reply_text("🎉 Aap Level 100 par pahunch gaye hain! Special badge ke liye /prestige command ka istemal karein!")
        
        session.commit()
    finally:
        session.close()

# 4. Economy and Advanced Features
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    shop_text = (
        "🛒 **ThePromotionHub Shop** 🛒\n\n"
        "Apne HubCoins se yeh items khareedo:\n\n"
        "1. **Title** (1000 Coins) - Ek hafte ke liye custom title.\n"
        "   `/buy title [Your Title]`\n\n"
        "2. **Spotlight** (2500 Coins) - Agle din ke spotlight mein guaranteed jagah.\n"
        "   `/buy spotlight`\n\n"
        "3. **VIP** (10000 Coins) - Permanent VIP status aur special perks.\n"
        "   `/buy vip`"
    )
    await update.message.reply_text(shop_text, parse_mode=ParseMode.MARKDOWN)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("Kya khareedna hai? Example: `/buy title My Awesome Title`")
        return

    item = args[0].lower()
    session = Session()
    try:
        db_user = get_or_create_user(session, update.effective_user)
        
        if item == "title":
            title_text = " ".join(args[1:])
            if not title_text:
                await update.message.reply_text("Title likhna zaroori hai. Example: `/buy title The King`")
                return
            if db_user.hubcoins < 1000:
                await update.message.reply_text(f"Iske liye 1000 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                return
            
            db_user.hubcoins -= 1000
            db_user.custom_title = title_text[:20] # Max 20 chars
            db_user.custom_title_expiry = datetime.now() + timedelta(days=7)
            session.commit()
            await update.message.reply_text(f"Badhai ho! Aapka naya title '{db_user.custom_title}' ek hafte ke liye set ho gaya hai.")

        elif item == "spotlight":
            if db_user.hubcoins < 2500:
                await update.message.reply_text(f"Iske liye 2500 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                return
            db_user.hubcoins -= 2500
            db_user.spotlight_priority = True
            session.commit()
            await update.message.reply_text("Kharidari safal! Aapko agle spotlight mein priority di jayegi. 🌟")
            
        elif item == "vip":
            if db_user.hubcoins < 10000:
                await update.message.reply_text(f"Iske liye 10000 HubCoins chahiye. Aapke paas {db_user.hubcoins} hain.")
                return
            db_user.hubcoins -= 10000
            db_user.vip_member = True
            session.commit()
            await update.message.reply_text("Welcome to the VIP club! 🎖️ Aapko ab special perks milenge.")
        
        else:
            await update.message.reply_text("Aisa koi item shop mein nahi hai. /shop dekho.")
    finally:
        session.close()

async def rep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await update.message.reply_text("Yeh command kisi message ko reply karke istemal karein.")
        return
        
    giver = update.effective_user
    receiver = update.message.reply_to_message.from_user
    
    if giver.id == receiver.id:
        await update.message.reply_text("Aap khud ko reputation nahi de sakte!")
        return
        
    session = Session()
    try:
        db_receiver = get_or_create_user(session, receiver)
        db_receiver.reputation += 1
        session.commit()
        await update.message.reply_to_message.reply_text(f"{receiver.first_name} ki reputation {giver.first_name} ne badhai! Current reputation: {db_receiver.reputation} 👍")
    finally:
        session.close()

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
        
        spotlight_text = (
            f"🌟 **Aaj ke Spotlight Member hain {selected_user.get_display_name()}!** 🌟\n\n"
            f"Yeh hamare group ke ek bahut active sadasya hain (Level: {selected_user.level}).\n\n"
            f"Chaliye, aaj hum sab milkar inko support karte hain! "
            f"Inke content ko check karein aur feedback dein!"
        )
        
        await context.bot.send_message(chat_id=GROUP_ID, text=spotlight_text, parse_mode=ParseMode.MARKDOWN)
        session.commit()
    except Exception as e:
        logger.error(f"Spotlight Error: {e}")
    finally:
        session.close()

# --- Main Application ---
def main() -> None:
    # NEW: Start the Flask web server in a separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Create the Telegram bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add all command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("prestige", prestige_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("coins", stats_command)) # /coins will also show stats
    application.add_handler(CommandHandler("rep", rep_command))

    # Add message handler for leveling up
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add handler for new members
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Add job queue for spotlight
    job_queue = application.job_queue
    # Run spotlight every 24 hours
    job_queue.run_repeating(spotlight_feature, interval=timedelta(hours=24), first=10)

    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
