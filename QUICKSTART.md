# 🎵 Python Music Bot - Quick Start Guide

## 🚀 Quick Setup (5 minutes)

### 1. Copy Environment File
```bash
cp env_example.txt .env
```

### 2. Edit .env File
Open `.env` and add your Discord bot token:
```
DISCORD_TOKEN=your_discord_bot_token_here
```

### 3. Run the Bot
```bash
python run.py
```

## 🎯 Features

- ✅ **Spotify Integration** - Play Spotify tracks via YouTube
- ✅ **YouTube Streaming** - Direct YouTube URL support  
- ✅ **Smart Search** - Find songs by name or artist
- ✅ **Queue Management** - Add, skip, stop songs
- ✅ **Reliable Streaming** - Uses yt-dlp (much more stable than Node.js libraries)

## 🎮 Commands

- `/play <song>` - Play a song
- `/skip` - Skip current song
- `/stop` - Stop and clear queue
- `/queue` - Show current queue
- `/testyt <url>` - Test YouTube URL

## 🔧 Why Python Version is Better

1. **More Reliable** - yt-dlp is more stable than Node.js YouTube libraries
2. **Better Error Handling** - Python's exception handling is more robust
3. **Easier Debugging** - Clear error messages and logging
4. **No Signature Issues** - yt-dlp handles YouTube changes automatically
5. **Better Performance** - More efficient memory usage

## 🆚 Comparison with Node.js Version

| Feature | Node.js | Python |
|---------|---------|--------|
| YouTube Streaming | ❌ Broken (signature issues) | ✅ Works perfectly |
| Spotify Integration | ✅ Works | ✅ Works |
| Error Handling | ⚠️ Complex | ✅ Simple |
| Setup | ⚠️ Many dependencies | ✅ Clean |
| Stability | ❌ Frequent breaks | ✅ Very stable |

## 🎵 Test It!

1. Join a voice channel
2. Use `/play Never Gonna Give You Up`
3. Enjoy music! 🎵

The Python version should work much better than the Node.js version!
