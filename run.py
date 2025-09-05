#!/usr/bin/env python3
"""
Simple run script for the Python Music Bot
"""

import os
import sys

def main():
    """Run the music bot"""
    print("🎵 Starting Python Music Bot...")
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("Please copy env_example.txt to .env and fill in your credentials.")
        return False
    
    # Check if Discord token is set
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv('DISCORD_TOKEN'):
        print("❌ DISCORD_TOKEN not found in .env file!")
        print("Please add your Discord bot token to the .env file.")
        return False
    
    # Import and run the bot
    try:
        from music_bot import bot
        print("✅ Bot configuration loaded successfully!")
        print("🚀 Starting bot...")
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
