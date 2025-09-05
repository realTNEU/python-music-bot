# Python Music Bot

A Discord music bot built with Python, discord.py, and yt-dlp for reliable YouTube streaming.

## Features

- 🎵 **Spotify Integration** - Search and play Spotify tracks via YouTube
- 🎥 **YouTube Streaming** - Direct YouTube URL support
- 🔍 **Smart Search** - Find songs by name, artist, or URL
- 📋 **Queue Management** - Add, skip, stop, and view queue
- 🧪 **Testing Commands** - Test YouTube streaming directly
- ⚡ **Reliable Streaming** - Uses yt-dlp for stable audio streaming

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `env_example.txt` to `.env` and fill in your credentials:

```bash
cp env_example.txt .env
```

Edit `.env`:
```
DISCORD_TOKEN=your_discord_bot_token_here
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
```

### 3. Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token to your `.env` file
5. Enable "Message Content Intent" and "Server Members Intent"
6. Invite bot to your server with these permissions:
   - Send Messages
   - Use Slash Commands
   - Connect
   - Speak
   - Use Voice Activity

### 4. Spotify API Setup (Optional)

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy Client ID and Client Secret to your `.env` file

### 5. Run the Bot

```bash
python music_bot.py
```

## Commands

### Slash Commands

- `/play <query>` - Play a song from Spotify or YouTube
- `/skip` - Skip the current song
- `/stop` - Stop playing and clear queue
- `/queue` - Show the current queue
- `/testyt <url>` - Test YouTube streaming with a direct URL
- `/sync` - Sync slash commands (owner only)

### Examples

- `/play Never Gonna Give You Up` - Search and play a song
- `/play https://open.spotify.com/track/...` - Play a Spotify track
- `/play https://youtube.com/watch?v=...` - Play a YouTube video
- `/testyt https://youtube.com/watch?v=dQw4w9WgXcQ` - Test YouTube streaming

## Features

### Music Queue
- Add multiple songs to queue
- Skip current song
- View queue status
- Automatic next song playback

### Spotify Integration
- Search Spotify tracks
- Play Spotify songs via YouTube
- Display Spotify metadata
- Link back to Spotify

### YouTube Streaming
- Direct YouTube URL support
- High-quality audio streaming
- Reliable yt-dlp backend
- Error handling and fallbacks

### Testing
- Test YouTube URLs directly
- Debug streaming issues
- Verify bot functionality

## Troubleshooting

### Common Issues

1. **Bot not responding to commands**
   - Check if bot has proper permissions
   - Ensure slash commands are synced with `/sync`
   - Verify bot token is correct

2. **Voice connection issues**
   - Make sure bot has "Connect" and "Speak" permissions
   - Check if voice channel is available
   - Verify bot is not already connected elsewhere

3. **YouTube streaming errors**
   - yt-dlp should handle most YouTube changes automatically
   - Check internet connection
   - Try different video URLs

4. **Spotify integration not working**
   - Verify Spotify credentials in `.env`
   - Check if Spotify API is working
   - Ensure track is available on YouTube

### Logs

The bot provides detailed logging:
- Search results
- Streaming status
- Error messages
- Command usage

Check console output for debugging information.

## Dependencies

- `discord.py` - Discord API wrapper
- `yt-dlp` - YouTube audio extraction
- `spotipy` - Spotify API wrapper
- `python-dotenv` - Environment variable management
- `youtube-search-python` - YouTube search
- `PyNaCl` - Voice encryption

## License

This project is for educational purposes. Please respect YouTube's Terms of Service and Discord's API Terms of Service.
