# FIXED BOT.PY FILE - EVENT LOOP ISSUES RESOLVED

import os
import asyncio
import random
import signal
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
        self.economy = EconomySystem(self.db)
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
        chat_id = update.effective_chat.id
        
        # Add user to database if not exists
        await self.db.add_user(user.id, user.first_name, chat_id, user.username)
        
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
            try:
                await context.bot.send_sticker(
                    chat_id=update.effective_chat.id,
                    sticker="CAACAgIAAxkBAAEBaZJlwqXzAAF"
                )
            except:
                pass  # Skip if sticker fails
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
        
        # Skip if user is a bot
        if update.effective_user.is_bot:
            return
        
        last_message_time = await self.db.get_last_message_time(user_id, chat_id)
        current_time = datetime.now()
        
        if last_message_time and (current_time - last_message_time < timedelta(seconds=60)):
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
            try:
                await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
            except:
                pass  # Skip if sticker fails
        
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
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        balance = await self.economy.get_balance(user_id, chat_id)
        
        balance_text = (
            f"💰 **{update.effective_user.first_name}'s Balance**\n\n"
            f"🪙 HubCoins: **{balance:,}**\n\n"
            f"Use /shop to spend your coins!"
        )
        await update.message.reply_text(balance_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🦁 **Levelup Leo Bot - Help** 🦁\n\n"
            "📊 **Commands:**\n"
            "/start - Bot ko start karein\n"
            "/level - Apna level check karein\n"
            "/top - Top 10 members dekhein\n"
            "/balance - Apne HubCoins check karein\n"
            "/shop - HubCoins shop\n"
            "/prestige - Prestige system (Level 100+)\n\n"
            "💡 **How it works:**\n"
            "• Har 60 seconds mein message karke XP paayein\n"
            "• XP se level up karein\n"
            "• Level up par HubCoins aur rewards paayein\n"
            "• Top leaderboard par pahunchein!\n\n"
            "Happy Leveling! 🚀"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def create_progress_bar(self, percentage):
        filled = int(percentage / 10)
        bar = "█" * filled + "▒" * (10 - filled)
        return f"[{bar}]"

    async def process_prestige(self, query, context):
        """Process prestige action"""
        user_id = int(query.data.split("_")[1])
        chat_id = query.message.chat_id
        
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data or user_data['level'] < 100:
            await query.edit_message_text(text="Prestige ke liye Level 100 hona zaroori hai!")
            return
        
        await self.db.process_prestige(user_id, chat_id)
        await query.edit_message_text(text="✨ Prestige successfully liya gaya! Aap Level 1 par reset ho gaye hain. Aapka prestige badge mil gaya! 🎖️")

    async def process_continue(self, query, context):
        """Process continue without prestige"""
        await query.edit_message_text(text="💪 Aapne continue karne ka faisla liya! Level 100+ ki journey shuru karein! 🚀")
    
    async def process_shop_purchase(self, query, context):
        """Process shop purchase action"""
        item = query.data.split("_")[1]
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        
        if item == "balance":
            balance = await self.economy.get_balance(user_id, chat_id)
            await query.edit_message_text(text=f"💰 Aapke paas **{balance}** HubCoins hain!", parse_mode='Markdown')
        else:
            await query.edit_message_text(text=f"Aapne '{item}' khareedne ke liye select kiya. Yeh feature jald hi aayega!")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("prestige_"):
            user_id = int(query.data.split("_")[1])
            if user_id == query.from_user.id:
                await self.process_prestige(query, context)
            else:
                await query.edit_message_text(text="Ye option sirf aapke liye hai!")
        
        elif query.data.startswith("continue_"):
            user_id = int(query.data.split("_")[1])
            if user_id == query.from_user.id:
                await self.process_continue(query, context)
            else:
                await query.edit_message_text(text="Ye option sirf aapke liye hai!")
        
        elif query.data.startswith("shop_"):
            await self.process_shop_purchase(query, context)

def main():
    """Initialize and run the bot - FIXED VERSION"""
    # Create bot instance
    bot = LevelupLeoBot()
    
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("level", bot.level_command))
    application.add_handler(CommandHandler("top", bot.top_command))
    application.add_handler(CommandHandler("shop", bot.shop_command))
    application.add_handler(CommandHandler("balance", bot.balance_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot.on_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))

    # Start the bot
    print("Bot is now running and polling for updates...")
    
    # Run the bot until Ctrl-C is pressed
    application.run_polling()

async def async_main():
    """Async version for proper database initialization"""
    bot = LevelupLeoBot()
    
    # Initialize database
    await bot.db.create_pool()
    await bot.db.setup_tables()
    print("Database initialized successfully!")
    
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("level", bot.level_command))
    application.add_handler(CommandHandler("top", bot.top_command))
    application.add_handler(CommandHandler("shop", bot.shop_command))
    application.add_handler(CommandHandler("balance", bot.balance_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot.on_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))

    # Start the bot
    print("Bot is now running and polling for updates...")
    
    # Run the bot
    await application.run_polling()

if __name__ == '__main__':
    try:
        # Use the async version for proper database initialization
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
    except Exception as e:
        print(f"Error: {e}")
