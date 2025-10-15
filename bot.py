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
            1: "CAACAgIAAxkBAAEBaZJlwqXzAAF",  # Replace with actual sticker IDs
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
            # Initialize user in database
            await self.db.add_user(member.id, member.first_name, update.effective_chat.id)
            
            welcome_msg = (
                f"🎊 Hey {member.first_name}, welcome to **{update.effective_chat.title}**! 🎊\n\n"
                f"Hmm, tumhari level to 0 hai. Message karo or apni level up karo 💪\n"
                f"ThePromotionHub mein active raho aur rewards jeeto! 🎁"
            )
            
            # Send welcome message with animated sticker
            await context.bot.send_sticker(
                chat_id=update.effective_chat.id,
                sticker="CAACAgIAAxkBAAEBaZJlwqXzAAF"  # Welcome sticker
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
        
        # Check cooldown (prevent spam)
        last_message_time = await self.db.get_last_message_time(user_id, chat_id)
        if last_message_time:
            time_diff = datetime.now() - last_message_time
            if time_diff < timedelta(seconds=60):  # 1 minute cooldown
                return
        
        # Award random XP (10-30)
        xp_gained = random.randint(10, 30)
        
        # Get current user data
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data:
            await self.db.add_user(user_id, user_name, chat_id)
            user_data = await self.db.get_user(user_id, chat_id)
        
        old_level = user_data['level']
        old_xp = user_data['xp']
        new_xp = old_xp + xp_gained
        
        # Calculate new level
        new_level = self.level_system.calculate_level(new_xp)
        
        # Award HubCoins for activity
        coins_earned = random.randint(1, 5)
        await self.economy.add_coins(user_id, chat_id, coins_earned)
        
        # Update database
        await self.db.update_xp(user_id, chat_id, new_xp, new_level)
        await self.db.update_last_message_time(user_id, chat_id)
        
        # Check for level up
        if new_level > old_level:
            await self.handle_level_up(
                update, context, user_id, user_name, 
                old_level, new_level, chat_id
            )
    
    async def handle_level_up(self, update, context, user_id, user_name, 
                            old_level, new_level, chat_id):
        """Handle level up events with Gemini-generated messages"""
        
        # Get appropriate sticker for this level
        sticker_id = None
        for level, sticker in self.level_stickers.items():
            if new_level == level:
                sticker_id = sticker
                break
        
        # Send animated sticker if available
        if sticker_id:
            await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
        
        # Generate unique message using Gemini API
        if new_level >= 50:
            level_message = await self.gemini.generate_levelup_message(
                user_name, new_level
            )
        else:
            # Pre-defined messages for lower levels
            level_messages = {
                5: f"🎯 {user_name} ne Level 5 achieve kiya! Shaandaar start hai! Keep going! 💪",
                10: f"🔥 WOW! {user_name} Level 10 pe pahunch gaye! Double digits mein entry! 🎊",
                15: f"⚡ {user_name} is on fire! Level 15 unlocked! Kya baat hai boss! 🚀",
                20: f"💥 Level 20! {user_name} to promotion ke master ban rahe hain! 👏",
                25: f"🌟 Quarter Century! {user_name} ne Level 25 complete kiya! Legend in making! 🏆",
                30: f"🎖️ Level 30 achieved! {user_name} ki growth dekh ke maza aa gaya! 💯",
                40: f"🚀 Level 40! {user_name} abhi to party shuru hui hai! Full power! 🔋",
            }
            
            level_message = level_messages.get(
                new_level, 
                f"🎉 Congratulations {user_name}! Level {new_level} achieved! Keep growing! 🌱"
            )
        
        # Check for special ranks (100+)
        special_rank = self.special_ranks.get(new_level)
        if special_rank:
            level_message += f"\n\n🏅 **Special Rank Unlocked**: {special_rank}"
        
        # Send level up message
        await context.bot.send_message(
            chat_id=chat_id,
            text=level_message,
            parse_mode='Markdown'
        )
        
        # Handle level 100 prestige option
        if new_level == 100:
            await self.offer_prestige(context, user_id, user_name, chat_id)
    
    async def offer_prestige(self, context, user_id, user_name, chat_id):
        """Offer prestige system at level 100"""
        keyboard = [
            [
                InlineKeyboardButton("✨ Take Prestige", callback_data=f"prestige_{user_id}"),
                InlineKeyboardButton("💪 Continue", callback_data=f"continue_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        prestige_text = (
            f"🎊 **LEGENDARY ACHIEVEMENT!** 🎊\n\n"
            f"{user_name}, you've reached Level 100! 🏆\n\n"
            f"Ab aapke paas 2 options hain:\n\n"
            f"✨ **Take Prestige**: Reset to Level 1 with a special badge\n"
            f"💪 **Continue**: Keep going beyond Level 100\n\n"
            f"Kya karna chahte ho?"
        )
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=prestige_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def level_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's current level and progress"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        user_data = await self.db.get_user(user_id, chat_id)
        if not user_data:
            await update.message.reply_text("Start chatting to earn XP! 💬")
            return
        
        level = user_data['level']
        xp = user_data['xp']
        prestige = user_data.get('prestige', 0)
        hubcoins = await self.economy.get_balance(user_id, chat_id)
        
        # Calculate XP needed for next level
        xp_for_next = self.level_system.xp_for_level(level + 1)
        xp_for_current = self.level_system.xp_for_level(level)
        xp_progress = xp - xp_for_current
        xp_needed = xp_for_next - xp_for_current
        
        # Create progress bar
        progress_percent = (xp_progress / xp_needed) * 100
        progress_bar = self.create_progress_bar(progress_percent)
        
        # Prestige badge
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
        """Show top 10 members leaderboard"""
        chat_id = update.effective_chat.id
        top_users = await self.db.get_top_users(chat_id, limit=10)
        
        if not top_users:
            await update.message.reply_text("No active members yet! Start chatting! 💬")
            return
        
        leaderboard = "🏆 **TOP 10 LEADERBOARD** 🏆\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(top_users):
            position_icon = medals[i] if i < 3 else f"{i+1}."
            prestige_stars = "⭐" * user.get('prestige', 0) if user.get('prestige', 0) > 0 else ""
            
            leaderboard += (
                f"{position_icon} **{user['name']}** {prestige_stars}\n"
                f"   Level {user['level']} • {user['xp']:,} XP\n\n"
            )
        
        await update.message.reply_text(leaderboard, parse_mode='Markdown')
    
    async def shop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display HubCoins shop"""
        keyboard = [
            [InlineKeyboardButton("📌 Spotlight Post (500 coins)", callback_data="shop_spotlight")],
            [InlineKeyboardButton("🏷️ Custom Title (1000 coins)", callback_data="shop_title")],
            [InlineKeyboardButton("🎁 Gift Coins (Variable)", callback_data="shop_gift")],
            [InlineKeyboardButton("🎨 Color Name (750 coins)", callback_data="shop_color")],
            [InlineKeyboardButton("💰 Check Balance", callback_data="shop_balance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        shop_text = (
            "🛍️ **HUBCOINS SHOP** 🛍️\n\n"
            "Spend your HubCoins on exclusive perks!\n\n"
            "💰 Earn coins by:\n"
            "• Being active in chat\n"
            "• Leveling up\n"
            "• Daily bonuses\n"
            "• Helping others\n\n"
            "Select an item to purchase:"
        )
        
        await update.message.reply_text(
            shop_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def spotlight_feature(self, context: ContextTypes.DEFAULT_TYPE):
        """Daily spotlight feature - runs automatically"""
        # This should be called by a job queue every 24 hours
        active_chats = await self.db.get_all_active_chats()
        
        for chat_id in active_chats:
            # Get random active user from last 24 hours
            spotlight_user = await self.db.get_random_active_user(chat_id, hours=24)
            
            if spotlight_user:
                spotlight_text = (
                    f"🌟 **TODAY'S SPOTLIGHT MEMBER** 🌟\n\n"
                    f"👤 @{spotlight_user['username'] or spotlight_user['name']}\n"
                    f"📊 Level: {spotlight_user['level']}\n"
                    f"✨ Total XP: {spotlight_user['xp']:,}\n\n"
                    f"🎉 Congratulations on being today's spotlight member!\n"
                    f"Keep being awesome! 💪"
                )
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=spotlight_text,
                    parse_mode='Markdown'
                )
    
    def create_progress_bar(self, percentage):
        """Create visual progress bar"""
        filled = int(percentage / 10)
        bar = "█" * filled + "▒" * (10 - filled)
        return f"[{bar}]"
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("prestige_"):
            user_id = int(query.data.split("_")<!--citation:1-->)
            if user_id == query.from_user.id:
                await self.process_prestige(query, context)
        
        elif query.data.startswith("shop_"):
            await self.process_shop_purchase(query, context)

async def main():
    """Initialize and run the bot"""
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Initialize bot
    bot = LevelupLeoBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("level", bot.level_command))
    application.add_handler(CommandHandler("top", bot.top_command))
    application.add_handler(CommandHandler("shop", bot.shop_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot.on_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    asyncio.run(main())
