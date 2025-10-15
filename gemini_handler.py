import google.generativeai as genai
import config
import random

class GeminiHandler:
    def __init__(self):
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
    
    async def generate_levelup_message(self, user_name, level):
        """Generate unique level-up message using Gemini"""
        
        prompts = [
            f"Write a short, funny, and motivating message in Hinglish for {user_name} who just reached Level {level} in a Telegram promotion group. Keep it under 50 words. Include emojis. Be creative and unique.",
            
            f"Create an exciting Hinglish congratulation message for {user_name} achieving Level {level}. Mix Hindi and English naturally. Add relevant emojis. Make it enthusiastic and encouraging.",
            
            f"Generate a creative level-up announcement for {user_name} reaching Level {level}. Use Hinglish language, be motivational, add humor if possible. Include 2-3 emojis.",
        ]
        
        try:
            prompt = random.choice(prompts)
            response = self.model.generate_content(prompt)
            
            if response and response.text:
                return response.text
            else:
                # Fallback messages
                fallback_messages = [
                    f"🔥 Amazing! {user_name} ne Level {level} achieve kar liya! Kya baat hai boss! 🚀",
                    f"🎉 Level {level} unlocked! {user_name} to fire hai bhai! Keep growing! 💪",
                    f"⚡ Woohoo! {user_name} reached Level {level}! Abhi to party shuru hui hai! 🎊",
                    f"🌟 Level {level} complete! {user_name} ki growth dekh ke maza aa gaya! 💯",
                ]
                return random.choice(fallback_messages)
                
        except Exception as e:
            print(f"Gemini API error: {e}")
            # Return a default message on error
            return f"🎉 Congratulations {user_name}! Level {level} achieved! Keep it up! 🚀"
