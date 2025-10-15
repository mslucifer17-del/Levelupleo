class EconomySystem:
    def __init__(self, db):
        self.db = db
        self.shop_items = {
            'spotlight': {'cost': 500, 'name': 'Spotlight Post', 'duration': 3600},
            'title': {'cost': 1000, 'name': 'Custom Title', 'duration': 604800},
            'color': {'cost': 750, 'name': 'Colored Name', 'duration': 259200},
        }
    
    async def add_coins(self, user_id, chat_id, amount):
        """Add HubCoins to user account"""
        async with self.db.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET hubcoins = hubcoins + $3
                WHERE user_id = $1 AND chat_id = $2
            ''', user_id, chat_id, amount)
    
    async def remove_coins(self, user_id, chat_id, amount):
        """Remove HubCoins from user account"""
        balance = await self.get_balance(user_id, chat_id)
        if balance < amount:
            return False
        
        async with self.db.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET hubcoins = hubcoins - $3
                WHERE user_id = $1 AND chat_id = $2
            ''', user_id, chat_id, amount)
        return True
    
    async def get_balance(self, user_id, chat_id):
        """Get user's HubCoin balance"""
        async with self.db.pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT hubcoins FROM users WHERE user_id = $1 AND chat_id = $2',
                user_id, chat_id
            )
            return result or 0
    
    async def process_purchase(self, user_id, chat_id, item_type):
        """Process shop purchase"""
        if item_type not in self.shop_items:
            return False, "Invalid item"
        
        item = self.shop_items[item_type]
        balance = await self.get_balance(user_id, chat_id)
        
        if balance < item['cost']:
            return False, "Insufficient HubCoins"
        
        success = await self.remove_coins(user_id, chat_id, item['cost'])
        if success:
            return True, f"Successfully purchased {item['name']}!"
        else:
            return False, "Purchase failed"
    
    async def gift_coins(self, sender_id, receiver_id, chat_id, amount):
        """Gift coins to another user"""
        sender_balance = await self.get_balance(sender_id, chat_id)
        
        if sender_balance < amount:
            return False, "Insufficient balance"
        
        await self.remove_coins(sender_id, chat_id, amount)
        await self.add_coins(receiver_id, chat_id, amount)
        return True, "Coins gifted successfully!"
