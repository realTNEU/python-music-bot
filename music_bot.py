import discord
from discord.ext import commands
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv
import json
import re
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import hashlib

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database class for MongoDB operations
class MusicDatabase:
    def __init__(self, mongodb_uri="mongodb://localhost:27017/musicbot"):
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client.musicbot
        self.songs = self.db.songs
        self.search_history = self.db.search_history
        
    async def connect(self):
        """Test database connection"""
        try:
            await self.client.admin.command('ping')
            logger.info("✅ MongoDB connected successfully")
            return True
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    async def close(self):
        """Close database connection"""
        self.client.close()
    
    def generate_song_id(self, title, artist, url):
        """Generate a unique ID for a song"""
        content = f"{title}_{artist}_{url}".lower()
        return hashlib.md5(content.encode()).hexdigest()
    
    async def save_song(self, song_data):
        """Save song data to database"""
        try:
            song_id = self.generate_song_id(
                song_data.get('title', ''),
                song_data.get('artist', ''),
                song_data.get('url', '')
            )
            
            song_doc = {
                '_id': song_id,
                'title': song_data.get('title', ''),
                'artist': song_data.get('artist', ''),
                'duration': song_data.get('duration', 0),
                'url': song_data.get('url', ''),
                'thumbnail': song_data.get('thumbnail', ''),
                'spotify_id': song_data.get('spotify_id', ''),
                'search_queries': [song_data.get('search_query', '').lower()],
                'play_count': 1,
                'first_searched': datetime.utcnow(),
                'last_played': datetime.utcnow(),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            # Use upsert to update if exists, insert if new
            result = await self.songs.update_one(
                {'_id': song_id},
                {
                    '$set': {
                        'title': song_doc['title'],
                        'artist': song_doc['artist'],
                        'duration': song_doc['duration'],
                        'url': song_doc['url'],
                        'thumbnail': song_doc['thumbnail'],
                        'spotify_id': song_doc['spotify_id'],
                        'last_played': song_doc['last_played'],
                        'updated_at': song_doc['updated_at']
                    },
                    '$inc': {'play_count': 1},
                    '$addToSet': {'search_queries': {'$each': song_doc['search_queries']}},
                    '$setOnInsert': {
                        'first_searched': song_doc['first_searched'],
                        'created_at': song_doc['created_at']
                    }
                },
                upsert=True
            )
            
            logger.info(f"💾 Song saved to database: {song_data.get('title', 'Unknown')}")
            return song_id
            
        except Exception as e:
            logger.error(f"Error saving song to database: {e}")
            return None
    
    async def search_songs(self, query, limit=5):
        """Search for songs in database"""
        try:
            query_lower = query.lower()
            
            # Search in title, artist, and search_queries
            search_filter = {
                '$or': [
                    {'title': {'$regex': query_lower, '$options': 'i'}},
                    {'artist': {'$regex': query_lower, '$options': 'i'}},
                    {'search_queries': {'$regex': query_lower, '$options': 'i'}}
                ]
            }
            
            cursor = self.songs.find(search_filter).sort('play_count', -1).limit(limit)
            songs = await cursor.to_list(length=limit)
            
            # Convert to the format expected by the bot
            results = []
            for song in songs:
                results.append({
                    'title': song.get('title', ''),
                    'artist': song.get('artist', ''),
                    'duration': song.get('duration', 0),
                    'url': song.get('url', ''),
                    'thumbnail': song.get('thumbnail', ''),
                    'spotify_id': song.get('spotify_id', ''),
                    'play_count': song.get('play_count', 0),
                    'from_cache': True
                })
            
            logger.info(f"🔍 Found {len(results)} cached songs for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Error searching songs in database: {e}")
            return []
    
    async def get_song_stats(self):
        """Get database statistics"""
        try:
            total_songs = await self.songs.count_documents({})
            total_plays = await self.songs.aggregate([
                {'$group': {'_id': None, 'total_plays': {'$sum': '$play_count'}}}
            ]).to_list(length=1)
            
            most_played = await self.songs.find().sort('play_count', -1).limit(5).to_list(length=5)
            
            return {
                'total_songs': total_songs,
                'total_plays': total_plays[0]['total_plays'] if total_plays else 0,
                'most_played': most_played
            }
            
        except Exception as e:
            logger.error(f"Error getting song stats: {e}")
            return {'total_songs': 0, 'total_plays': 0, 'most_played': []}
    
    async def log_search(self, query, results_count, from_cache=False):
        """Log search activity"""
        try:
            search_doc = {
                'query': query,
                'results_count': results_count,
                'from_cache': from_cache,
                'timestamp': datetime.utcnow()
            }
            await self.search_history.insert_one(search_doc)
        except Exception as e:
            logger.error(f"Error logging search: {e}")

# Initialize database
db = MusicDatabase(os.getenv('MONGODB_URI', 'mongodb://localhost:27017/musicbot'))

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize music players dictionary
bot.music_players = {}

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_USER_ID = os.getenv('SPOTIFY_USER_ID')

# Initialize Spotify client
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    client_credentials_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    logger.info("✅ Spotify API authenticated successfully")
else:
    sp = None
    logger.warning("⚠️ Spotify credentials not found, Spotify features disabled")

# Music queue class
class MusicQueue:
    def __init__(self):
        self.songs = []
        self.current_song = None
        self.playing = False
        self.volume = 0.5
        self.voice_client = None
        self.text_channel = None

    def add_song(self, song):
        self.songs.append(song)
        logger.info(f"Added song to queue: {song['title']}")

    def next_song(self):
        if self.songs:
            self.current_song = self.songs.pop(0)
            return self.current_song
        return None

    def clear(self):
        self.songs.clear()
        self.current_song = None
        self.playing = False

# Global queues for each guild
queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = MusicQueue()
    return queues[guild_id]

# YouTube search function using yt-dlp with database caching
async def search_youtube(query, max_results=5):
    """Search YouTube for videos using yt-dlp with database caching"""
    try:
        logger.info(f"🔍 Searching YouTube for: {query}")
        
        # First, try to find in database cache
        cached_results = await db.search_songs(query, limit=max_results)
        if cached_results:
            logger.info(f"📦 Found {len(cached_results)} cached results for: {query}")
            await db.log_search(query, len(cached_results), from_cache=True)
            return cached_results
        
        # If not in cache, search YouTube
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Search YouTube
            search_results = ydl.extract_info(
                f"ytsearch{max_results}:{query}",
                download=False
            )
            
            if not search_results or 'entries' not in search_results:
                logger.warning("No YouTube results found")
                await db.log_search(query, 0, from_cache=False)
                return []
            
            formatted_results = []
            for entry in search_results['entries']:
                if entry:  # Skip None entries
                    song_data = {
                        'title': entry.get('title', 'Unknown Title'),
                        'url': entry.get('url', ''),
                        'duration': entry.get('duration', 0),
                        'artist': entry.get('uploader', 'Unknown Artist'),
                        'thumbnail': entry.get('thumbnail', ''),
                        'search_query': query,
                        'from_cache': False
                    }
                    formatted_results.append(song_data)
                    
                    # Save to database asynchronously
                    asyncio.create_task(db.save_song(song_data))
            
            logger.info(f"✅ Found {len(formatted_results)} YouTube results")
            await db.log_search(query, len(formatted_results), from_cache=False)
            return formatted_results
            
    except Exception as e:
        logger.error(f"Error searching YouTube: {e}")
        await db.log_search(query, 0, from_cache=False)
        return []

# Spotify search function
async def search_spotify(query):
    """Search Spotify for tracks"""
    if not sp:
        logger.warning("Spotify not available")
        return None
    
    try:
        logger.info(f"🔍 Searching Spotify for: {query}")
        results = sp.search(q=query, type='track', limit=1)
        
        if not results['tracks']['items']:
            logger.warning("No Spotify results found")
            return None
        
        track = results['tracks']['items'][0]
        return {
            'title': track['name'],
            'artist': ', '.join([artist['name'] for artist in track['artists']]),
            'url': track['external_urls']['spotify'],
            'spotify_id': track['id'],
            'duration': f"{track['duration_ms'] // 60000}:{track['duration_ms'] % 60000 // 1000:02d}",
            'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else ''
        }
    except Exception as e:
        logger.error(f"Error searching Spotify: {e}")
        return None

# YouTube audio stream function
async def get_youtube_audio(url):
    """Get audio stream from YouTube URL using yt-dlp"""
    try:
        logger.info(f"🎵 Getting audio stream from: {url}")
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'extractaudio': True,
            'audioformat': 'm4a',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info
            info = ydl.extract_info(url, download=False)
            
            # Find the best audio format
            audio_url = None
            for format_info in info.get('formats', []):
                if format_info.get('acodec') != 'none' and format_info.get('vcodec') == 'none':
                    audio_url = format_info.get('url')
                    break
            
            if not audio_url:
                # Fallback to any audio format
                for format_info in info.get('formats', []):
                    if format_info.get('acodec') != 'none':
                        audio_url = format_info.get('url')
                        break
            
            if not audio_url:
                raise Exception("No audio stream found")
            
            logger.info("✅ Audio stream URL obtained")
            return audio_url, info
            
    except Exception as e:
        logger.error(f"Error getting YouTube audio: {e}")
        raise

# Music player class
class MusicPlayer:
    def __init__(self, voice_client, text_channel):
        self.voice_client = voice_client
        self.text_channel = text_channel
        self.queue = None
        self.control_message = None
        self.manual_skip = False  # Flag to prevent after_song from running during manual skip

    async def play_song(self, song):
        """Play a song from the queue"""
        try:
            if not self.voice_client or not self.voice_client.is_connected():
                logger.error("Voice client not connected")
                return
            
            # Get audio stream URL
            audio_url = await self.get_audio_url(song['url'])
            
            if not audio_url:
                await self.text_channel.send("❌ Failed to get audio stream")
                await self.next_song()
                return
            
            # Create audio source from URL using requests
            audio_source = await self.create_audio_source(audio_url)
            
            if not audio_source:
                await self.text_channel.send("❌ Failed to create audio source")
                await self.next_song()
                return
            
            # Play the audio
            self.voice_client.play(audio_source, after=self.after_song)
            
            # Store current song in queue for controls
            if self.queue:
                self.queue.current_song = song
            
            # Create beautiful embed with proper thumbnail
            embed = discord.Embed(
                title="🎵 Now Playing",
                color=0x1DB954,  # Spotify green
                timestamp=discord.utils.utcnow()
            )
            
            # Main song info with better formatting
            embed.description = f"**{song['title']}**"
            
            # Artist info
            if song.get('artist'):
                embed.add_field(name="🎤 Artist", value=song['artist'], inline=True)
            
            # Duration info
            if song.get('duration'):
                duration_str = f"{int(song['duration'])//60}:{int(song['duration'])%60:02d}"
                embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
            
            # Source info with cache indicator
            source_text = "🎵 YouTube"
            if song.get('spotify_id'):
                source_text = "🎵 YouTube (via Spotify)"
            if song.get('from_cache', False):
                source_text += " 📦"
            embed.add_field(name="📡 Source", value=source_text, inline=True)
            
            # Set thumbnail as main image using song URL for YouTube thumbnail
            if song.get('url'):
                # Extract video ID from YouTube URL for thumbnail
                if 'youtube.com/watch?v=' in song['url']:
                    video_id = song['url'].split('v=')[1].split('&')[0]
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                    embed.set_image(url=thumbnail_url)
                elif song.get('thumbnail'):
                    embed.set_image(url=song['thumbnail'])
            
            # Add Spotify link if available
            if song.get('spotify_id'):
                embed.add_field(name="🔗 Links", value=f"[Open in Spotify]({song['url']})", inline=False)
            
            # Footer with bot info
            embed.set_footer(
                text="🎵 TNEU Music Bot • Playing with Copyright laws • Use buttons to control",
                icon_url=bot.user.avatar.url if bot.user.avatar else None
            )
            
            # Create control buttons
            class MusicControls(discord.ui.View):
                def __init__(self, music_player):
                    super().__init__(timeout=None)
                    self.music_player = music_player
                
                @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary, custom_id="pause_btn")
                async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    try:
                        if not interaction.user.voice or not interaction.user.voice.channel:
                            await interaction.response.send_message("❌ You need to be in a voice channel to control music!", ephemeral=True)
                            return
                        
                        if interaction.user.voice.channel != self.music_player.voice_client.channel:
                            await interaction.response.send_message("❌ You need to be in the same voice channel as the bot!", ephemeral=True)
                            return
                        
                        if self.music_player.voice_client.is_playing():
                            self.music_player.voice_client.pause()
                            button.label = "▶️ Resume"
                            button.style = discord.ButtonStyle.success
                            await interaction.response.edit_message(view=self)
                            await interaction.followup.send("⏸️ Music paused!", ephemeral=True)
                        elif self.music_player.voice_client.is_paused():
                            self.music_player.voice_client.resume()
                            button.label = "⏸️ Pause"
                            button.style = discord.ButtonStyle.primary
                            await interaction.response.edit_message(view=self)
                            await interaction.followup.send("▶️ Music resumed!", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Error in pause button: {e}")
                        try:
                            if not interaction.response.is_done():
                                await interaction.response.send_message("❌ An error occurred while pausing!", ephemeral=True)
                        except:
                            pass
                
                @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary, custom_id="skip_btn")
                async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    try:
                        if not interaction.user.voice or not interaction.user.voice.channel:
                            await interaction.response.send_message("❌ You need to be in a voice channel to control music!", ephemeral=True)
                            return
                        
                        if interaction.user.voice.channel != self.music_player.voice_client.channel:
                            await interaction.response.send_message("❌ You need to be in the same voice channel as the bot!", ephemeral=True)
                            return
                        
                        if self.music_player.voice_client.is_playing() or self.music_player.voice_client.is_paused():
                            # Respond to interaction first
                            await interaction.response.defer(ephemeral=True)
                            
                            # Set manual skip flag to prevent after_song callback
                            self.music_player.manual_skip = True
                            logger.info(f"Manual skip flag set. Queue has {len(self.music_player.queue.songs) if self.music_player.queue and hasattr(self.music_player.queue, 'songs') else 0} songs")
                            
                            # Stop current song
                            self.music_player.voice_client.stop()
                            
                            # Small delay to ensure after_song callback is processed
                            await asyncio.sleep(0.1)
                            
                            # Get next song from queue
                            if self.music_player.queue and hasattr(self.music_player.queue, 'songs') and self.music_player.queue.songs:
                                logger.info(f"Queue still has {len(self.music_player.queue.songs)} songs after stop")
                                # Use the queue's next_song method which handles the queue properly
                                next_song = self.music_player.queue.next_song()
                                if next_song:
                                    logger.info(f"Playing next song: {next_song['title']}")
                                    # Play next song
                                    await self.music_player.play_song(next_song)
                                    # Reset manual skip flag after playing
                                    self.music_player.manual_skip = False
                                    
                                    # Create updated embed for the new song
                                    updated_embed = discord.Embed(
                                        title="🎵 Now Playing",
                                        color=0x1DB954,
                                        timestamp=discord.utils.utcnow()
                                    )
                                    
                                    updated_embed.description = f"**{next_song['title']}**"
                                    
                                    if next_song.get('artist'):
                                        updated_embed.add_field(name="🎤 Artist", value=next_song['artist'], inline=True)
                                    
                                    if next_song.get('duration'):
                                        duration_str = f"{int(next_song['duration'])//60}:{int(next_song['duration'])%60:02d}"
                                        updated_embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
                                    
                                    source_text = "🎵 YouTube"
                                    if next_song.get('spotify_id'):
                                        source_text = "🎵 YouTube (via Spotify)"
                                    if next_song.get('from_cache', False):
                                        source_text += " 📦"
                                    updated_embed.add_field(name="📡 Source", value=source_text, inline=True)
                                    
                                    # Set thumbnail using song URL for YouTube thumbnail
                                    if next_song.get('url'):
                                        # Extract video ID from YouTube URL for thumbnail
                                        if 'youtube.com/watch?v=' in next_song['url']:
                                            video_id = next_song['url'].split('v=')[1].split('&')[0]
                                            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                                            updated_embed.set_image(url=thumbnail_url)
                                        elif next_song.get('thumbnail'):
                                            updated_embed.set_image(url=next_song['thumbnail'])
                                    
                                    if next_song.get('spotify_id'):
                                        updated_embed.add_field(name="🔗 Links", value=f"[Open in Spotify]({next_song['url']})", inline=False)
                                    
                                    updated_embed.set_footer(
                                        text="🎵 TNEU Music Bot • Playing with Copyright laws • Use buttons to control",
                                        icon_url=bot.user.avatar.url if bot.user.avatar else None
                                    )
                                    
                                    # Create new view with fresh buttons
                                    new_view = MusicControls(self.music_player)
                                    
                                    # Update the original message with new embed and buttons
                                    try:
                                        await interaction.edit_original_response(embed=updated_embed, view=new_view)
                                        await interaction.followup.send(f"⏭️ Skipped! Now playing: **{next_song['title']}**", ephemeral=True)
                                    except:
                                        # If we can't edit the original message, send a new one
                                        await interaction.followup.send(embed=updated_embed, view=new_view)
                                        await interaction.followup.send(f"⏭️ Skipped! Now playing: **{next_song['title']}**", ephemeral=True)
                                else:
                                    logger.info("No next song found")
                                    if hasattr(self.music_player.queue, 'playing'):
                                        self.music_player.queue.playing = False
                                    await interaction.followup.send("⏭️ Song skipped! Queue is now empty.", ephemeral=True)
                            else:
                                logger.info("Queue is empty or invalid")
                                if hasattr(self.music_player.queue, 'playing'):
                                    self.music_player.queue.playing = False
                                await interaction.followup.send("⏭️ Song skipped! Queue is now empty.", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Error in skip button: {e}")
                        try:
                            if not interaction.response.is_done():
                                await interaction.response.send_message("❌ An error occurred while skipping!", ephemeral=True)
                        except:
                            pass
                
                @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="stop_btn")
                async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    try:
                        if not interaction.user.voice or not interaction.user.voice.channel:
                            await interaction.response.send_message("❌ You need to be in a voice channel to control music!", ephemeral=True)
                            return
                        
                        if interaction.user.voice.channel != self.music_player.voice_client.channel:
                            await interaction.response.send_message("❌ You need to be in the same voice channel as the bot!", ephemeral=True)
                            return
                        
                        if self.music_player.voice_client:
                            self.music_player.voice_client.stop()
                        
                        if self.music_player.queue and hasattr(self.music_player.queue, 'songs'):
                            self.music_player.queue.songs.clear()
                            if hasattr(self.music_player.queue, 'playing'):
                                self.music_player.queue.playing = False
                        
                        await interaction.response.send_message("⏹️ Music stopped and queue cleared!", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Error in stop button: {e}")
                        try:
                            if not interaction.response.is_done():
                                await interaction.response.send_message("❌ An error occurred while stopping!", ephemeral=True)
                        except:
                            pass
                
                @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh_btn")
                async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    try:
                        if not interaction.user.voice or not interaction.user.voice.channel:
                            await interaction.response.send_message("❌ You need to be in a voice channel to control music!", ephemeral=True)
                            return
                        
                        if interaction.user.voice.channel != self.music_player.voice_client.channel:
                            await interaction.response.send_message("❌ You need to be in the same voice channel as the bot!", ephemeral=True)
                            return
                        
                        if self.music_player.queue and self.music_player.queue.current_song:
                            current_song = self.music_player.queue.current_song
                            
                            # Create updated embed
                            updated_embed = discord.Embed(
                                title="🎵 Now Playing",
                                color=0x1DB954,
                                timestamp=discord.utils.utcnow()
                            )
                            
                            updated_embed.description = f"**{current_song['title']}**"
                            
                            if current_song.get('artist'):
                                updated_embed.add_field(name="🎤 Artist", value=current_song['artist'], inline=True)
                            
                            if current_song.get('duration'):
                                duration_str = f"{int(current_song['duration'])//60}:{int(current_song['duration'])%60:02d}"
                                updated_embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
                            
                            source_text = "🎵 YouTube"
                            if current_song.get('spotify_id'):
                                source_text = "🎵 YouTube (via Spotify)"
                            if current_song.get('from_cache', False):
                                source_text += " 📦"
                            updated_embed.add_field(name="📡 Source", value=source_text, inline=True)
                            
                            # Set thumbnail using song URL for YouTube thumbnail
                            if current_song.get('url'):
                                # Extract video ID from YouTube URL for thumbnail
                                if 'youtube.com/watch?v=' in current_song['url']:
                                    video_id = current_song['url'].split('v=')[1].split('&')[0]
                                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                                    updated_embed.set_image(url=thumbnail_url)
                                elif current_song.get('thumbnail'):
                                    updated_embed.set_image(url=current_song['thumbnail'])
                            
                            if current_song.get('spotify_id'):
                                updated_embed.add_field(name="🔗 Links", value=f"[Open in Spotify]({current_song['url']})", inline=False)
                            
                            updated_embed.set_footer(
                                text="🎵 TNEU Music Bot • Playing with Copyright laws • Use buttons to control",
                                icon_url=bot.user.avatar.url if bot.user.avatar else None
                            )
                            
                            await interaction.response.edit_message(embed=updated_embed, view=self)
                            await interaction.followup.send("🔄 Control panel refreshed!", ephemeral=True)
                        else:
                            await interaction.response.send_message("❌ No song currently playing!", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Error in refresh button: {e}")
                        try:
                            if not interaction.response.is_done():
                                await interaction.response.send_message("❌ An error occurred while refreshing!", ephemeral=True)
                        except:
                            pass
            
            # Create view with buttons
            view = MusicControls(self)
            
            # Send embed with buttons
            message = await self.text_channel.send(embed=embed, view=view)
            
            # Store the control message for this player
            self.control_message = message
            
            logger.info(f"✅ Now playing: {song['title']}")
            
        except Exception as e:
            logger.error(f"Error playing song: {e}")
            await self.text_channel.send(f"❌ Error playing song: {str(e)}")
            await self.next_song()

    async def get_audio_url(self, url):
        """Get direct audio URL using yt-dlp"""
        try:
            logger.info(f"🎵 Getting audio stream URL from: {url}")
            
            ydl_opts = {
                'format': 'bestaudio[ext=webm]/bestaudio[ext=mp4]/bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Find the best audio format for Discord
                audio_url = None
                best_format = None
                
                # Prefer formats that work well with Discord
                for format_info in info.get('formats', []):
                    if format_info.get('acodec') != 'none' and format_info.get('vcodec') == 'none':
                        # Prefer Opus codec (works best with Discord)
                        if format_info.get('acodec') == 'opus':
                            audio_url = format_info.get('url')
                            best_format = format_info
                            break
                        elif not audio_url:  # Fallback to any audio-only format
                            audio_url = format_info.get('url')
                            best_format = format_info
                
                if not audio_url:
                    # Last resort: any audio format
                    for format_info in info.get('formats', []):
                        if format_info.get('acodec') != 'none':
                            audio_url = format_info.get('url')
                            best_format = format_info
                            break
                
                if not audio_url:
                    raise Exception("No audio stream found")
                
                logger.info(f"✅ Audio stream URL obtained - Format: {best_format.get('ext', 'unknown')}, Codec: {best_format.get('acodec', 'unknown')}")
                return audio_url
                
        except Exception as e:
            logger.error(f"Error getting audio URL: {e}")
            return None

    async def create_audio_source(self, audio_url):
        """Create audio source from URL using FFmpegPCMAudio"""
        try:
            logger.info(f"🔗 Creating audio source from URL")
            
            # Use FFmpegPCMAudio with Discord-compatible options
            # These options ensure stable audio without tempo changes
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2 -avoid_negative_ts make_zero',
                'options': '-vn -f s16le -ar 48000 -ac 2 -af "aresample=48000,asetrate=48000"'
            }
            
            audio_source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
            
            logger.info("✅ Audio source created successfully")
            return audio_source
            
        except Exception as e:
            logger.error(f"Error creating audio source: {e}")
            return None

    def after_song(self, error):
        """Called after a song finishes playing"""
        # Don't auto-advance if this was a manual skip
        if hasattr(self, 'manual_skip') and self.manual_skip:
            logger.info("Skipping after_song callback due to manual skip")
            return
            
        if error:
            logger.error(f"Error in after_song: {error}")
            # If there's an error, try to reconnect
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.handle_voice_error())
            except:
                pass
        else:
            # Play next song in queue
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.next_song())
            except:
                pass
    
    async def handle_voice_error(self):
        """Handle voice connection errors"""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            
            # Wait a bit before trying to reconnect
            await asyncio.sleep(2)
            
            # Try to reconnect and play next song
            await self.next_song()
            
        except Exception as e:
            logger.error(f"Error handling voice error: {e}")
            await self.text_channel.send("❌ Voice connection error. Please try rejoining the voice channel.")

    async def next_song(self):
        """Play the next song in the queue"""
        if self.queue and self.queue.songs:
            next_song = self.queue.next_song()
            if next_song:
                await self.play_song(next_song)
            else:
                self.queue.playing = False
                await self.text_channel.send("🎵 Queue finished!")
        else:
            self.queue.playing = False

# Bot events
@bot.event
async def on_ready():
    logger.info(f"🎵 Music Bot is ready! Logged in as {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")
    
    # Connect to MongoDB
    await db.connect()
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} slash commands!")
        for cmd in synced:
            logger.info(f"  - /{cmd.name}: {cmd.description}")
    except Exception as e:
        logger.error(f"❌ Error syncing commands: {e}")
    
    # Set bot status
    activity = discord.Activity(type=discord.ActivityType.listening, name="Playing with Copyright laws")
    await bot.change_presence(activity=activity)

async def ensure_bot_deafened(voice_client):
    """Ensure the bot is deafened in the voice channel"""
    try:
        if voice_client and voice_client.is_connected():
            await voice_client.guild.change_voice_state(
                channel=voice_client.channel, 
                self_deaf=True
            )
            logger.info("Bot deafened itself to avoid audio feedback")
    except Exception as e:
        logger.error(f"Failed to deafen bot: {e}")

async def get_spotify_playlists():
    """Get user's public Spotify playlists"""
    try:
        if not sp or not SPOTIFY_USER_ID:
            return None, "Spotify not configured or user ID not set"
        
        playlists = sp.user_playlists(SPOTIFY_USER_ID, limit=50)
        playlist_list = []
        
        for playlist in playlists['items']:
            playlist_info = {
                'id': playlist['id'],
                'name': playlist['name'],
                'description': playlist.get('description', ''),
                'tracks': playlist['tracks']['total'],
                'public': playlist['public'],
                'owner': playlist['owner']['display_name'],
                'external_urls': playlist['external_urls']['spotify']
            }
            playlist_list.append(playlist_info)
        
        return playlist_list, None
    except Exception as e:
        logger.error(f"Error fetching Spotify playlists: {e}")
        return None, str(e)

async def get_playlist_tracks(playlist_id):
    """Get tracks from a specific Spotify playlist"""
    try:
        if not sp:
            return None, "Spotify not configured"
        
        tracks = []
        results = sp.playlist_tracks(playlist_id, limit=100)
        
        while results:
            for item in results['items']:
                track = item['track']
                if track and track['type'] == 'track':
                    track_info = {
                        'title': track['name'],
                        'artist': ', '.join([artist['name'] for artist in track['artists']]),
                        'duration': track['duration_ms'] / 1000,
                        'spotify_id': track['id'],
                        'external_urls': track['external_urls']['spotify']
                    }
                    tracks.append(track_info)
            
            if results['next']:
                results = sp.next(results)
            else:
                break
        
        return tracks, None
    except Exception as e:
        logger.error(f"Error fetching playlist tracks: {e}")
        return None, str(e)

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates"""
    if member == bot.user:
        # Ensure bot stays deafened when it joins a voice channel
        if after.channel and not before.channel:
            voice_client = member.guild.voice_client
            if voice_client and voice_client.is_connected():
                await ensure_bot_deafened(voice_client)
        return
    
    # If bot was disconnected, clear the queue
    if before.channel and not after.channel:
        guild_id = member.guild.id
        if guild_id in queues:
            queues[guild_id].clear()

# Removed reaction handler - now using Discord buttons instead

# Slash commands
@bot.tree.command(name="play", description="Play a song from Spotify or YouTube")
async def play(interaction: discord.Interaction, query: str):
    """Play a song"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You need to be in a voice channel to play music!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Get or create voice channel
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            voice_client = await voice_channel.connect()
            # Deafen the bot to avoid audio feedback
            await ensure_bot_deafened(voice_client)
        
        # Get queue
        queue = get_queue(interaction.guild.id)
        queue.voice_client = voice_client
        queue.text_channel = interaction.channel
        
        # Create or get music player
        if not hasattr(bot, 'music_players'):
            bot.music_players = {}
        
        if interaction.guild.id not in bot.music_players:
            player = MusicPlayer(voice_client, interaction.channel)
            bot.music_players[interaction.guild.id] = player
        else:
            player = bot.music_players[interaction.guild.id]
            player.voice_client = voice_client
            player.text_channel = interaction.channel
        
        # Assign queue to music player
        player.queue = queue
        
        # Check if it's a Spotify URL
        spotify_track = None
        if 'spotify.com' in query:
            if sp:
                try:
                    track_id = query.split('/')[-1].split('?')[0]
                    track = sp.track(track_id)
                    spotify_track = {
                        'title': track['name'],
                        'artist': ', '.join([artist['name'] for artist in track['artists']]),
                        'url': track['external_urls']['spotify'],
                        'spotify_id': track['id'],
                        'duration': f"{track['duration_ms'] // 60000}:{track['duration_ms'] % 60000 // 1000:02d}",
                        'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else ''
                    }
                except Exception as e:
                    logger.error(f"Error getting Spotify track: {e}")
                    await interaction.followup.send("❌ Invalid Spotify URL")
                    return
            else:
                await interaction.followup.send("❌ Spotify integration not available")
                return
        
        # Search for YouTube equivalent
        if spotify_track:
            search_query = f"{spotify_track['title']} {spotify_track['artist']}"
            youtube_results = await search_youtube(search_query, max_results=1)
            
            if not youtube_results:
                await interaction.followup.send("❌ Could not find YouTube equivalent for this Spotify track")
                return
            
            # Use the first result
            youtube_song = youtube_results[0]
            youtube_song.update(spotify_track)  # Add Spotify info
            song = youtube_song
        else:
            # Direct search
            youtube_results = await search_youtube(query, max_results=1)
            
            if not youtube_results:
                await interaction.followup.send("❌ No results found for your query")
                return
            
            song = youtube_results[0]
        
        # Add to queue
        queue.add_song(song)
        
        # Create music player
        player = MusicPlayer(voice_client, interaction.channel)
        player.queue = queue
        
        # Store player
        if not hasattr(bot, 'music_players'):
            bot.music_players = {}
        bot.music_players[interaction.guild.id] = player
        
        # Play if not already playing
        if not queue.playing:
            queue.playing = True
            await player.play_song(song)
            await interaction.followup.send(f"🎵 Added to queue: **{song['title']}**")
        else:
            await interaction.followup.send(f"🎵 Added to queue: **{song['title']}** (Position: {len(queue.songs)})")
    
    except Exception as e:
        logger.error(f"Error in play command: {e}")
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")

@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    """Skip current song"""
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    interaction.guild.voice_client.stop()
    await interaction.response.send_message("⏭️ Skipped current song!")

@bot.tree.command(name="stop", description="Stop playing and clear the queue")
async def stop(interaction: discord.Interaction):
    """Stop playing and clear queue"""
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot is not in a voice channel!", ephemeral=True)
        return
    
    # Clear queue
    queue = get_queue(interaction.guild.id)
    queue.clear()
    
    # Stop playing
    interaction.guild.voice_client.stop()
    
    # Disconnect
    await interaction.guild.voice_client.disconnect()
    
    await interaction.response.send_message("🛑 Stopped playing and cleared queue!")

@bot.tree.command(name="queue", description="Show the current queue with pagination")
async def queue(interaction: discord.Interaction, page: int = 1):
    """Show current queue with pagination"""
    queue = get_queue(interaction.guild.id)
    
    if not queue.songs and not queue.current_song:
        await interaction.response.send_message("📭 Queue is empty!", ephemeral=True)
        return
    
    # Pagination settings
    songs_per_page = 10
    total_songs = len(queue.songs)
    total_pages = max(1, (total_songs + songs_per_page - 1) // songs_per_page)
    
    # Validate page number
    if page < 1 or page > total_pages:
        await interaction.response.send_message(f"❌ Invalid page number! Please use 1-{total_pages}", ephemeral=True)
        return
    
    # Calculate song range for current page
    start_idx = (page - 1) * songs_per_page
    end_idx = min(start_idx + songs_per_page, total_songs)
    current_page_songs = queue.songs[start_idx:end_idx]
    
    embed = discord.Embed(
        title="🎵 Music Queue", 
        color=0x1DB954,
        timestamp=discord.utils.utcnow()
    )
    
    # Add current song info
    if queue.current_song:
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{queue.current_song['title']}**",
            inline=False
        )
        
        # Add artist and duration info if available
        if queue.current_song.get('artist'):
            embed.add_field(name="🎤 Artist", value=queue.current_song['artist'], inline=True)
        
        if queue.current_song.get('duration'):
            duration_str = f"{int(queue.current_song['duration'])//60}:{int(queue.current_song['duration'])%60:02d}"
            embed.add_field(name="⏱️ Duration", value=duration_str, inline=True)
        
        # Set thumbnail using song URL for YouTube thumbnail
        if queue.current_song.get('url'):
            # Extract video ID from YouTube URL for thumbnail
            if 'youtube.com/watch?v=' in queue.current_song['url']:
                video_id = queue.current_song['url'].split('v=')[1].split('&')[0]
                thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                embed.set_image(url=thumbnail_url)
            elif queue.current_song.get('thumbnail'):
                embed.set_image(url=queue.current_song['thumbnail'])
    
    # Add queue songs for current page
    if current_page_songs:
        queue_text = ""
        for i, song in enumerate(current_page_songs, start_idx + 1):
            status = "⏳"
            duration_str = f"{int(song.get('duration', 0))//60}:{int(song.get('duration', 0))%60:02d}" if song.get('duration') else "Unknown"
            artist = song.get('artist', 'Unknown')
            queue_text += f"{status} {i}. **{song['title']}**\n🎤 {artist} • ⏱️ {duration_str}\n\n"
        
        embed.add_field(name=f"📝 Up Next (Page {page}/{total_pages})", value=queue_text, inline=False)
    
    # Add control info
    embed.add_field(
        name="🎮 Controls", 
        value="⏯️ /pause • /resume • ⏭️ /skip • ⏹️ /stop", 
        inline=False
    )
    
    # Add pagination info
    if total_pages > 1:
        embed.add_field(
            name="📄 Pagination",
            value=f"Use `/queue page:{page+1}` for next page • `/queue page:{page-1}` for previous page",
            inline=False
        )
    
    embed.set_footer(
        text=f"🎵 TNEU Music Bot • {total_songs} songs in queue • Page {page}/{total_pages}",
        icon_url=bot.user.avatar.url if bot.user.avatar else None
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="testyt", description="Test YouTube streaming with a direct URL")
async def testyt(interaction: discord.Interaction, url: str):
    """Test YouTube streaming"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You need to be in a voice channel to test YouTube streaming!", ephemeral=True)
        return
    
    if 'youtube.com' not in url and 'youtu.be' not in url:
        await interaction.response.send_message("❌ Please provide a valid YouTube URL!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Get or create voice channel
        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            voice_client = await voice_channel.connect()
            # Deafen the bot to avoid audio feedback
            await ensure_bot_deafened(voice_client)
        
        # Create test song
        test_song = {
            'title': 'Test Song',
            'artist': 'Test Artist',
            'url': url,
            'duration': 'Unknown'
        }
        
        # Get queue and add song
        queue = get_queue(interaction.guild.id)
        queue.voice_client = voice_client
        queue.text_channel = interaction.channel
        queue.add_song(test_song)
        
        # Create music player
        player = MusicPlayer(voice_client, interaction.channel)
        player.queue = queue
        
        # Store player
        if not hasattr(bot, 'music_players'):
            bot.music_players = {}
        bot.music_players[interaction.guild.id] = player
        
        # Play if not already playing
        if not queue.playing:
            queue.playing = True
            await player.play_song(test_song)
            await interaction.followup.send(f"🧪 Testing YouTube URL: {url}")
        else:
            await interaction.followup.send(f"🧪 Added test song to queue: {url}")
    
    except Exception as e:
        logger.error(f"Error in testyt command: {e}")
        await interaction.followup.send(f"❌ Error testing YouTube streaming: {str(e)}")

# Additional control commands
@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    """Pause the current song"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    if not hasattr(bot, 'music_players') or interaction.guild.id not in bot.music_players:
        await interaction.response.send_message("❌ No music player found for this server!", ephemeral=True)
        return
    
    player = bot.music_players[interaction.guild.id]
    if not player.voice_client or not player.voice_client.is_playing():
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    player.voice_client.pause()
    await interaction.response.send_message("⏸️ Music paused!")

@bot.tree.command(name="resume", description="Resume the current song")
async def resume(interaction: discord.Interaction):
    """Resume the current song"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    if not hasattr(bot, 'music_players') or interaction.guild.id not in bot.music_players:
        await interaction.response.send_message("❌ No music player found for this server!", ephemeral=True)
        return
    
    player = bot.music_players[interaction.guild.id]
    if not player.voice_client or not player.voice_client.is_paused():
        await interaction.response.send_message("❌ Nothing is currently paused!", ephemeral=True)
        return
    
    player.voice_client.resume()
    await interaction.response.send_message("▶️ Music resumed!")

@bot.tree.command(name="volume", description="Set the volume (0-100)")
async def volume(interaction: discord.Interaction, level: int):
    """Set the volume level"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    if level < 0 or level > 100:
        await interaction.response.send_message("❌ Volume must be between 0 and 100!", ephemeral=True)
        return
    
    if not hasattr(bot, 'music_players') or interaction.guild.id not in bot.music_players:
        await interaction.response.send_message("❌ No music player found for this server!", ephemeral=True)
        return
    
    player = bot.music_players[interaction.guild.id]
    if not player.voice_client or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    # Note: Discord.py doesn't have built-in volume control
    # This is a placeholder for future implementation
    await interaction.response.send_message(f"🔊 Volume set to {level}% (Note: Volume control not yet implemented in Discord.py)")

@bot.tree.command(name="stats", description="Show music database statistics")
async def stats(interaction: discord.Interaction):
    """Show database statistics"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    try:
        stats_data = await db.get_song_stats()
        
        embed = discord.Embed(
            title="📊 Music Database Statistics",
            color=0x1DB954,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="🎵 Total Songs", value=f"{stats_data['total_songs']:,}", inline=True)
        embed.add_field(name="▶️ Total Plays", value=f"{stats_data['total_plays']:,}", inline=True)
        embed.add_field(name="📦 Cache Status", value="✅ Active", inline=True)
        
        if stats_data['most_played']:
            most_played_text = ""
            for i, song in enumerate(stats_data['most_played'][:5], 1):
                most_played_text += f"{i}. **{song.get('title', 'Unknown')}**\n🎤 {song.get('artist', 'Unknown')} • 🔢 {song.get('play_count', 0)} plays\n\n"
            
            embed.add_field(name="🏆 Most Played Songs", value=most_played_text, inline=False)
        
        embed.set_footer(
            text="🎵 TNEU Music Bot • Database powered by MongoDB",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await interaction.response.send_message("❌ Error retrieving statistics!", ephemeral=True)

@bot.tree.command(name="search", description="Search the music database")
async def search_db(interaction: discord.Interaction, query: str):
    """Search the music database"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    try:
        results = await db.search_songs(query, limit=10)
        
        if not results:
            await interaction.response.send_message(f"❌ No songs found for: {query}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🔍 Search Results for: {query}",
            color=0x1DB954,
            timestamp=discord.utils.utcnow()
        )
        
        for i, song in enumerate(results[:5], 1):
            duration_str = f"{int(song.get('duration', 0))//60}:{int(song.get('duration', 0))%60:02d}" if song.get('duration') else "Unknown"
            play_count = song.get('play_count', 0)
            cache_indicator = "📦" if song.get('from_cache', False) else "🆕"
            
            embed.add_field(
                name=f"{cache_indicator} {i}. {song.get('title', 'Unknown')}",
                value=f"🎤 {song.get('artist', 'Unknown')} • ⏱️ {duration_str} • 🔢 {play_count} plays",
                inline=False
            )
        
        if len(results) > 5:
            embed.set_footer(text=f"... and {len(results) - 5} more results")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error searching database: {e}")
        await interaction.response.send_message("❌ Error searching database!", ephemeral=True)

@bot.tree.command(name="clear_cache", description="Clear the music database cache")
async def clear_cache(interaction: discord.Interaction):
    """Clear the music database cache"""
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return
    
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    try:
        # Clear songs collection
        result = await db.songs.delete_many({})
        await interaction.response.send_message(f"🗑️ Cleared {result.deleted_count} songs from cache!")
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        await interaction.response.send_message("❌ Error clearing cache!", ephemeral=True)

# TNEU command - List and play Spotify playlists
@bot.tree.command(name="tneu", description="List your Spotify playlists and play them")
async def tneu(interaction: discord.Interaction):
    """List Spotify playlists and allow playing them"""
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You need to be in a voice channel to use this command!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Get playlists
        playlists, error = await get_spotify_playlists()
        
        if error:
            await interaction.followup.send(f"❌ Error fetching playlists: {error}", ephemeral=True)
            return
        
        if not playlists:
            await interaction.followup.send("❌ No playlists found or Spotify not configured!", ephemeral=True)
            return
        
        # Create embed with playlists
        embed = discord.Embed(
            title="🎵 Your Spotify Playlists",
            color=0x1DB954,
            timestamp=discord.utils.utcnow()
        )
        
        embed.description = "Click the buttons below to play a playlist!"
        
        # Add playlist info
        for i, playlist in enumerate(playlists[:10], 1):  # Limit to 10 playlists
            track_count = playlist['tracks']
            public_status = "🌐 Public" if playlist['public'] else "🔒 Private"
            
            embed.add_field(
                name=f"{i}. {playlist['name']}",
                value=f"🎵 {track_count} tracks • {public_status}\n👤 {playlist['owner']}",
                inline=False
            )
        
        if len(playlists) > 10:
            embed.set_footer(text=f"Showing 10 of {len(playlists)} playlists")
        else:
            embed.set_footer(text=f"Total: {len(playlists)} playlists")
        
        # Create view with playlist selection buttons
        class PlaylistSelector(discord.ui.View):
            def __init__(self, playlists):
                super().__init__(timeout=300)  # 5 minutes timeout
                self.playlists = playlists
            
            @discord.ui.select(
                placeholder="Select a playlist to play...",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label=playlist['name'][:100],  # Discord limit
                        description=f"{playlist['tracks']} tracks • {playlist['owner']}",
                        value=str(i)
                    ) for i, playlist in enumerate(playlists[:25])  # Discord limit
                ]
            )
            async def select_playlist(self, interaction: discord.Interaction, select: discord.ui.Select):
                await interaction.response.defer()
                
                try:
                    playlist_index = int(select.values[0])
                    selected_playlist = self.playlists[playlist_index]
                    
                    # Get voice client
                    voice_channel = interaction.user.voice.channel
                    voice_client = interaction.guild.voice_client
                    
                    if not voice_client or not voice_client.is_connected():
                        voice_client = await voice_channel.connect()
                        await ensure_bot_deafened(voice_client)
                    
                    # Get queue
                    queue = get_queue(interaction.guild.id)
                    queue.voice_client = voice_client
                    queue.text_channel = interaction.channel
                    
                    # Get playlist tracks
                    tracks, error = await get_playlist_tracks(selected_playlist['id'])
                    
                    if error:
                        await interaction.followup.send(f"❌ Error fetching playlist tracks: {error}", ephemeral=True)
                        return
                    
                    if not tracks:
                        await interaction.followup.send("❌ No tracks found in this playlist!", ephemeral=True)
                        return
                    
                    # Add tracks to queue
                    added_count = 0
                    for track in tracks:
                        # Search for YouTube equivalent
                        search_query = f"{track['title']} {track['artist']}"
                        youtube_results = await search_youtube(search_query, 1)
                        
                        if youtube_results:
                            song = youtube_results[0]
                            song['spotify_id'] = track['spotify_id']
                            song['spotify_url'] = track['external_urls']
                            queue.add_song(song)
                            added_count += 1
                    
                    if added_count == 0:
                        await interaction.followup.send("❌ No songs could be found on YouTube for this playlist!", ephemeral=True)
                        return
                    
                    # Create or get music player
                    if not hasattr(bot, 'music_players'):
                        bot.music_players = {}
                    
                    if interaction.guild.id not in bot.music_players:
                        player = MusicPlayer(voice_client, interaction.channel)
                        bot.music_players[interaction.guild.id] = player
                    else:
                        player = bot.music_players[interaction.guild.id]
                        player.voice_client = voice_client
                        player.text_channel = interaction.channel
                    
                    # Assign queue to music player
                    player.queue = queue
                    
                    # Start playing if nothing is playing
                    if not queue.playing and queue.songs:
                        next_song = queue.next_song()
                        if next_song:
                            await player.play_song(next_song)
                    
                    await interaction.followup.send(
                        f"✅ Added **{added_count}** songs from **{selected_playlist['name']}** to the queue!\n"
                        f"🎵 Playlist: {selected_playlist['name']}\n"
                        f"📊 Total tracks: {len(tracks)}\n"
                        f"✅ Added to queue: {added_count}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error playing playlist: {e}")
                    await interaction.followup.send(f"❌ Error playing playlist: {str(e)}", ephemeral=True)
        
        view = PlaylistSelector(playlists)
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Error in tneu command: {e}")
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

# Sync commands
@bot.tree.command(name="sync", description="Sync slash commands")
async def sync(interaction: discord.Interaction):
    """Sync slash commands"""
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    try:
        synced = await bot.tree.sync()
        await interaction.response.send_message(f"✅ Synced {len(synced)} commands!")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to sync commands: {str(e)}")

# Run the bot
if __name__ == "__main__":
    # Get bot token
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        exit(1)
    
    # Set bot owner ID (replace with your Discord user ID)
    bot.owner_id = 123456789012345678  # Replace with your Discord user ID
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Error running bot: {e}")
