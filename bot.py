# SAHI BOT.PY FILE - ISE COPY KAREIN

import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import Database
from level_system import LevelSystem
from economy import EconomySystem
from gemini_handler import GeminiHandler
import config

class LevelupLeoBot:
    def __init__(self):
        self.db = Database()
        self.level_system = LevelSystem()
        self.economy = EconomySystem()
        self.gemini = GeminiHandler()
        
        # Animated stickers for different levels
        self.level_stickers = {
            1: "CAACAgIAAxkBAAEBaZJlwqXzAAF",
            5: "CAACAgIAAxkBAAEBaZJlwqXzAAG",
            10: "CAACAgIAAxkBAAEBaZJlwqXzAAH",
            25: "CAACAgIAAxkBAAEBaZJlwqXzAAI",
            50: "CAACAgIAAxkBAAEBaZJlwqXzAAJ",
            75: "CAACAgIAAxkBAAEBaZJlwqXzAAK",
            100: "CAACAgIAAxkBAAEBaZJlwqXzAAL"
        }
        
        # Special ranks after level 100
        self.special_ranks = {
            100: "🎖️ Pro Promoter",
            110: "🌟 Promotion Guru",
            125: "👑 The Legend",
            150: "💎 Diamond Elite",
            200: "🔥 Unstoppable Force"
        }
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        welcome_text = (
            f"🎉 Welcome to **Levelup Leo Bot**! 🎉\n\n"
            f"Hey {user.first_name}! Mein hun Leo, tumhara level-up companion! 🦁\n\n"
            f"📊 Commands:\n"
            f"/level - Check your current level\n"
            f"/top - Top 10 members leaderboard\n"
            f"/shop - HubCoins shop\n"
            f"/balance - Check your HubCoins\n"
            f"/prestige - Prestige system (Level 100+)\n"
            f"/help - All commands\n\n"
            f"💪 Start chatting to earn XP and level up!"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
    async def on_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome new members"""
        for member in update.message.new_chat_members:
            await self.db.add_user(member.id, member.first_name, update.effective_chat.id, member.username)
            welcome_msg = (
                f"🎊 Hey {member.first_name}, welcome to **{update.effective_chat.title}**! 🎊\n\n"
                f"Hmm, tumhari level to 0 hai. Message karo or apni level up karo 💪\n"
                f"ThePromotionHub mein active raho aur rewards jeeto! 🎁"
            )
            await context.bot.send_sticker(
                chat_id=update.effective_chat.id,
                sticker="CAACAgIAAxkBAAEBaZJlwqXzAAF"
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome_msg,
                parse_mode='Markdown'
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process all non-command messages for XP"""
        if not update.message or not update.message.text:
            return
            
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        chat_id = update.effective_chat.id
        
        last_message_time = await self.db.get_last_message_time(user_id, chat_id)
        if last_message_time and (datetime.now() - last_message_time < timedelta(seconds=60)):
            return
        
        xp_gained = random.randint(10, 30)
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data:
            await self.db.add_user(user_id, user_name, chat_id, update.effective_user.username)
            user_data = await self.db.get_user(user_id, chat_id)
        
        old_level = user_data['level']
        new_xp = user_data['xp'] + xp_gained
        new_level = self.level_system.calculate_level(new_xp)
        
        coins_earned = random.randint(1, 5)
        await self.economy.add_coins(user_id, chat_id, coins_earned)
        
        await self.db.update_xp(user_id, chat_id, new_xp, new_level)
        await self.db.update_last_message_time(user_id, chat_id)
        
        if new_level > old_level:
            await self.handle_level_up(update, context, user_id, user_name, old_level, new_level, chat_id)
    
    async def handle_level_up(self, update, context, user_id, user_name, old_level, new_level, chat_id):
        sticker_id = self.level_stickers.get(new_level)
        if sticker_id:
            await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
        
        if new_level >= 50:
            level_message = await self.gemini.generate_levelup_message(user_name, new_level)
        else:
            level_messages = {
                5: f"🎯 {user_name} ne Level 5 achieve kiya! Shaandaar start hai! Keep going! 💪",
                10: f"🔥 WOW! {user_name} Level 10 pe pahunch gaye! Double digits mein entry! 🎊",
                25: f"🌟 Quarter Century! {user_name} ne Level 25 complete kiya! Legend in making! 🏆",
            }
            level_message = level_messages.get(new_level, f"🎉 Congratulations {user_name}! Level {new_level} achieved! Keep growing! 🌱")
        
        special_rank = self.special_ranks.get(new_level)
        if special_rank:
            level_message += f"\n\n🏅 **Special Rank Unlocked**: {special_rank}"
        
        await context.bot.send_message(chat_id=chat_id, text=level_message, parse_mode='Markdown')
        
        if new_level == 100:
            await self.offer_prestige(context, user_id, user_name, chat_id)
    
    async def offer_prestige(self, context, user_id, user_name, chat_id):
        keyboard = [[
            InlineKeyboardButton("✨ Take Prestige", callback_data=f"prestige_{user_id}"),
            InlineKeyboardButton("💪 Continue", callback_data=f"continue_{user_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        prestige_text = (
            f"🎊 **LEGENDARY ACHIEVEMENT!** 🎊\n\n"
            f"{user_name}, you've reached Level 100! 🏆\n\n"
            f"✨ **Take Prestige**: Reset to Level 1 with a special badge\n"
            f"💪 **Continue**: Keep going beyond Level 100\n\n"
            f"Kya karna chahte ho?"
        )
        await context.bot.send_message(chat_id=chat_id, text=prestige_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def level_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data:
            await update.message.reply_text("Start chatting to earn XP! 💬")
            return
        
        level, xp, prestige = user_data['level'], user_data['xp'], user_data.get('prestige', 0)
        hubcoins = await self.economy.get_balance(user_id, chat_id)
        
        xp_for_next = self.level_system.xp_for_level(level + 1)
        xp_for_current = self.level_system.xp_for_level(level)
        xp_progress = xp - xp_for_current
        xp_needed = xp_for_next - xp_for_current
        
        progress_percent = (xp_progress / xp_needed) * 100 if xp_needed > 0 else 100
        progress_bar = self.create_progress_bar(progress_percent)
        prestige_badge = "🌟" * prestige if prestige > 0 else ""
        
        level_text = (
            f"📊 **{update.effective_user.first_name}'s Stats** {prestige_badge}\n\n"
            f"🎯 Level: **{level}**\n"
            f"✨ Total XP: **{xp:,}**\n"
            f"💰 HubCoins: **{hubcoins:,}**\n"
            f"🎖️ Prestige: **{prestige}**\n\n"
            f"📈 Progress to Level {level + 1}:\n"
            f"{progress_bar}\n"
            f"{xp_progress}/{xp_needed} XP ({progress_percent:.1f}%)"
        )
        await update.message.reply_text(level_text, parse_mode='Markdown')
    
    async def top_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        top_users = await self.db.get_top_users(update.effective_chat.id, limit=10)
        if not top_users:
            await update.message.reply_text("No active members yet! Start chatting! 💬")
            return
        
        leaderboard = "🏆 **TOP 10 LEADERBOARD** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(top_users):
            position_icon = medals[i] if i < 3 else f"{i+1}."
            prestige_stars = "⭐" * user.get('prestige', 0)
            leaderboard += (
                f"{position_icon} **{user['name']}** {prestige_stars}\n"
                f"   Level {user['level']} • {user['xp']:,} XP\n\n"
            )
        await update.message.reply_text(leaderboard, parse_mode='Markdown')
    
    async def shop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📌 Spotlight Post (500 coins)", callback_data="shop_spotlight")],
            [InlineKeyboardButton("🏷️ Custom Title (1000 coins)", callback_data="shop_title")],
            [InlineKeyboardButton("🎁 Gift Coins (Variable)", callback_data="shop_gift")],
            [InlineKeyboardButton("💰 Check Balance", callback_data="shop_balance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        shop_text = (
            "🛍️ **HUBCOINS SHOP** 🛍️\n\n"
            "Spend your HubCoins on exclusive perks!\n\n"
            "Select an item to purchase:"
        )
        await update.message.reply_text(shop_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    def create_progress_bar(self, percentage):
        filled = int(percentage / 10)
        bar = "█" * filled + "▒" * (10 - filled)
        return f"[{bar}]"

    # ✅ IN FUNCTIONS KO CLASS KE ANDAR MOVE KAR DIYA GAYA HAI
    async def process_prestige(self, query, context):
        """Process prestige action"""
        # Yahan prestige ka logic aayega
        await query.edit_message_text(text="Prestige successfully liya gaya! Aap Level 1 par reset ho gaye hain. ✨")

    async def process_shop_purchase(self, query, context):
        """Process shop purchase action"""
        # Yahan shop ka logic aayega
        item = query.data.split("_")[1]
        await query.edit_message_text(text=f"Aapne '{item}' khareedne ke liye select kiya. Yeh feature jald hi aayega!")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("prestige_"):
            user_id = int(query.data.split("_")[1])
            if user_id == query.from_user.id:
                await self.process_prestige(query, context)
        
        elif query.data.startswith("shop_"):
            await self.process_shop_purchase(query, context)

# === REPLACE THE OLD 'main' FUNCTION AND '__main__' BLOCK WITH THIS ===

async def main():
    """Initialize and run the bot's components correctly."""
    # 1. Initialize the main bot class
    bot = LevelupLeoBot()

    # 2. Setup the database connection pool
    await bot.db.create_pool()
    await bot.db.setup_tables()

    # 3. Build the Telegram application
    application = Application.builder().token(config.BOT_TOKEN).build()

    # 4. Add all your command and message handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("level", bot.level_command))
    application.add_handler(CommandHandler("top", bot.top_command))
    application.add_handler(CommandHandler("shop", bot.shop_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot.on_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))

    # 5. Use the application's context manager for clean startup and shutdown
    async with application:
        await application.initialize()  # Prepares the bot
        await application.start()       # Starts the background tasks for handlers
        await application.updater.start_polling() # Starts fetching updates

        print("Bot is now running and polling for updates...")

        # Keep the bot running forever until it's stopped
        await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
