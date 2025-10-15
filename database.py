import asyncpg
import os
from datetime import datetime
import config

class Database:
    def __init__(self):
        self.pool = None
    
    async def create_pool(self):
        """Create database connection pool"""
        self.pool = await asyncpg.create_pool(
            config.DATABASE_URL,
            min_size=10,
            max_size=20
        )
    
    async def setup_tables(self):
        """Create necessary database tables"""
        async with self.pool.acquire() as conn:
            # Users table with comprehensive data
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT,
                    chat_id BIGINT,
                    name VARCHAR(255),
                    username VARCHAR(255),
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    prestige INTEGER DEFAULT 0,
                    hubcoins INTEGER DEFAULT 0,
                    last_message TIMESTAMP,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    custom_title VARCHAR(100),
                    spotlight_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                )
            ''')
            
            # Transaction history for economy
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    chat_id BIGINT,
                    type VARCHAR(50),
                    amount INTEGER,
                    description TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Spotlight history
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS spotlight_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    chat_id BIGINT,
                    date DATE DEFAULT CURRENT_DATE
                )
            ''')
    
    async def add_user(self, user_id, name, chat_id, username=None):
        """Add new user to database"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, chat_id, name, username)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, chat_id) DO UPDATE
                SET name = $3, username = $4
            ''', user_id, chat_id, name, username)
    
    async def get_user(self, user_id, chat_id):
        """Get user data"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1 AND chat_id = $2',
                user_id, chat_id
            )
    
    async def update_xp(self, user_id, chat_id, new_xp, new_level):
        """Update user XP and level"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET xp = $3, level = $4, last_message = CURRENT_TIMESTAMP
                WHERE user_id = $1 AND chat_id = $2
            ''', user_id, chat_id, new_xp, new_level)
    
    async def get_top_users(self, chat_id, limit=10):
        """Get top users by XP"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT name, username, xp, level, prestige
                FROM users
                WHERE chat_id = $1
                ORDER BY prestige DESC, level DESC, xp DESC
                LIMIT $2
            ''', chat_id, limit)
            return [dict(row) for row in rows]
    
    async def get_last_message_time(self, user_id, chat_id):
        """Get user's last message timestamp"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT last_message FROM users WHERE user_id = $1 AND chat_id = $2',
                user_id, chat_id
            )
            return result
    
    async def update_last_message_time(self, user_id, chat_id):
        """Update last message timestamp"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET last_message = CURRENT_TIMESTAMP WHERE user_id = $1 AND chat_id = $2',
                user_id, chat_id
            )
    
    async def process_prestige(self, user_id, chat_id):
        """Process prestige for user"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET level = 1, xp = 0, prestige = prestige + 1
                WHERE user_id = $1 AND chat_id = $2
            ''', user_id, chat_id)
    
    async def get_random_active_user(self, chat_id, hours=24):
        """Get random active user for spotlight"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow('''
                SELECT * FROM users
                WHERE chat_id = $1 
                AND last_message > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                ORDER BY RANDOM()
                LIMIT 1
            ''', chat_id, hours)
    
    async def get_all_active_chats(self):
        """Get all active chat IDs"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT DISTINCT chat_id FROM users WHERE last_message > CURRENT_TIMESTAMP - INTERVAL \'7 days\''
            )
            return [row['chat_id'] for row in rows]
