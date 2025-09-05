#!/usr/bin/env python3
"""
Script to sync Discord slash commands
"""
import asyncio
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user}")
    print("Syncing commands...")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands!")
        print("Commands synced:")
        for cmd in synced:
            print(f"  - /{cmd.name}: {cmd.description}")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    
    await bot.close()

async def main():
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ DISCORD_TOKEN not found in .env file!")
        return
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
