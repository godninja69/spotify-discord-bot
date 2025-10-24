import discord
from discord.ext import commands, tasks # Import commands and tasks
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials # Use Client Credentials Flow
import os
import asyncio
import re # Import regex for link parsing
import traceback # Import for detailed error logging

# --- Environment Variables / Secrets ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
# !!! REPLACE with your actual Discord Channel ID (as an integer) !!!
NOTIFICATION_CHANNEL_ID = 123456789012345678 # Use the actual ID here

# --- Global Variables ---
# Use a set to store artist URIs for easy adding/removing and avoiding duplicates
# !!! REPLACE with your initial Spotify Artist URIs or leave empty !!!
artists_to_track_set = {
    # "spotify:artist:ExampleArtistID1",
    # "spotify:artist:ExampleArtistID2"
}

# Use a set to store IDs of already announced releases
announced_release_ids = set()

# --- Spotify Authentication ---
sp = None # Initialize sp to None
try:
    if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        # Test connection by fetching a known artist (optional but good for debugging)
        sp.artist("spotify:artist:06HL4z0CvFAxyc27GXpf02") # Example: Tame Impala ID
        print("✅ Spotify connection successful using Client Credentials.")
    else:
        print("⚠️ Spotify Client ID or Secret not found in environment variables.")
except Exception as e:
    print(f"❌ Error initializing Spotify Client Credentials: {e}")
    sp = None # Ensure sp is None if auth fails

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True # REQUIRED for reading command messages
# Make sure to enable this intent in the Discord Developer Portal for your bot!

bot = commands.Bot(command_prefix="!", intents=intents) # Define command prefix (e.g., !)

# --- Bot Functions & Background Task ---

async def check_new_releases():
    """Checks Spotify for new releases from tracked artists."""
    global announced_release_ids
    global artists_to_track_set
    if sp is None: # Don't run if Spotify connection failed
        print("❌ Spotify connection unavailable, skipping release check.")
        return

    print("Checking for new releases...")
    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        print(f"❌ Error: Could not find channel with ID {NOTIFICATION_CHANNEL_ID}. Make sure the ID is correct and the bot is in the server.")
        return

    # Convert set to list for iteration to avoid issues if set changes mid-loop
    current_artists_to_track = list(artists_to_track_set)
    if not current_artists_to_track:
        print("No artists currently being tracked.")
        return

    for artist_uri in current_artists_to_track:
        artist_id = artist_uri.split(':')[-1] # Get ID from URI
        try:
            # Get latest 5 albums and singles
            results = sp.artist_albums(artist_id, album_type='album,single', limit=5, country='US')
            artist_info = sp.artist(artist_id)
            artist_name = artist_info.get('name', f'Unknown Artist ({artist_id})')

            if results and results['items']:
                for item in results['items']:
                    release_id = item['id']
                    release_name = item['name']
                    release_type = item['album_type']
                    release_url = item['external_urls']['spotify']
                    # release_date = item.get('release_date', 'N/A') # Optional: Release date can be inconsistent

                    # Check if already announced
                    if release_id not in announced_release_ids:
                        print(f"✅ Found potential new release: {artist_name} - {release_name}")
                        message = (
                            f"🚨 **New {release_type.capitalize()} Release!** 🚨\n\n"
                            f"**Artist:** {artist_name}\n"
                            f"**Title:** {release_name}\n"
                            # f"**Released:** {release_date}\n" # Optional
                            f"🔗 Listen here: {release_url}"
                        )
                        try:
                            await channel.send(message)
                            announced_release_ids.add(release_id)
                            print(f"   Sent notification to channel {NOTIFICATION_CHANNEL_ID}.")
                            await asyncio.sleep(1) # Small delay between messages to avoid Discord rate limits
                        except discord.errors.Forbidden:
                            print(f"   ❌ Error: Bot lacks permissions to send messages in channel {NOTIFICATION_CHANNEL_ID}.")
                            # Stop trying for this channel if permissions are wrong
                            break
                        except Exception as send_e:
                            print(f"   ❌ Error sending message: {send_e}")

            # Short delay between checking each artist to avoid Spotify rate limits
            await asyncio.sleep(0.5)

        except spotipy.exceptions.SpotifyException as se:
            print(f"   ❌ Spotify API Error checking artist {artist_uri}: Status {se.http_status}, Reason: {se.msg}")
            # Consider specific handling for 429 (rate limit) or 404 (not found)
            await asyncio.sleep(10) # Wait longer on API errors
        except Exception as e:
            print(f"   ❌ General Error checking artist {artist_uri}: {type(e).__name__} - {e}")
            await asyncio.sleep(5)

    print("Finished checking releases cycle.")


@tasks.loop(hours=1) # Checks once per hour
async def background_check_loop():
    """Runs the check_new_releases function periodically."""
    await check_new_releases()

@background_check_loop.before_loop
async def before_background_check_loop():
    """Waits until the bot is ready before starting the loop."""
    print("Background task: Waiting for bot to be ready...")
    await bot.wait_until_ready()
    print("Background task: Bot ready, starting loop.")

# --- Discord Events ---

@bot.event
async def on_ready():
    """Runs when the bot successfully connects to Discord."""
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    if not background_check_loop.is_running():
        print("Starting background release check loop...")
        try:
            background_check_loop.start()
        except Exception as e:
            print(f"❌ Failed to start background loop: {e}")

# --- Discord Commands ---

@bot.command(name='addartists', help='Adds one or more Spotify artist links/URIs to the tracking list.\nExample: !addartists <link1> <URI2> ...')
async def add_artists(ctx, *, artist_links: str):
    """Adds one or
