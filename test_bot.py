import requests
import json

def test_bot():
    """Test if bot is responding"""
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual token
    
    # Get bot info
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    response = requests.get(url)
    
    if response.status_code == 200:
        bot_info = response.json()
        if bot_info['ok']:
            bot_name = bot_info['result']['first_name']
            print(f"✅ Bot {bot_name} is active and responding!")
            print(f"🤖 Username: @{bot_info['result']['username']}")
        else:
            print("❌ Bot token is invalid")
    else:
        print("❌ Cannot connect to Telegram API")

def get_updates():
    """Check recent updates"""
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual token
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    
    if response.status_code == 200:
        updates = response.json()
        if updates['ok'] and updates['result']:
            print(f"📨 Found {len(updates['result'])} updates:")
            for update in updates['result']:
                if 'message' in update:
                    msg = update['message']
                    chat_type = msg['chat']['type']
                    chat_title = msg['chat'].get('title', 'Private')
                    print(f"  💬 {chat_title} ({chat_type}): {msg.get('text', 'No text')}")
        else:
            print("📭 No recent updates found")
    else:
        print("❌ Cannot get updates")

if __name__ == '__main__':
    test_bot()
    print("\n" + "="*50 + "\n")
    get_updates()
