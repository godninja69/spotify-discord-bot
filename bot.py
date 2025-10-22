import discord
from discord.ext import commands, tasks # Import commands and tasks
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials # Use Client Credentials Flow
import os
import asyncio
import re # Import regex for link parsing

# --- Environment Variables / Secrets ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
# !!! REPLACE with your actual Discord Channel ID (as an integer) !!!
NOTIFICATION_CHANNEL_ID = 123456789012345678

# --- Global Variables ---
# Use a set to store artist URIs for easy adding/removing and avoiding duplicates
# !!! REPLACE with your initial Spotify Artist URIs or leave empty !!!
artists_to_track_set = {
    # "spotify:artist:ArtistID1",
    # "spotify:artist:ArtistID2"
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
        print(f"❌ Error: Could not find channel with ID {NOTIFICATION_CHANNEL_ID}")
        return

    # Convert set to list for iteration to avoid issues if set changes mid-loop
    current_artists_to_track = list(artists_to_track_set)
    if not current_artists_to_track:
        print("No artists currently being tracked.")
        return

    for artist_uri in current_artists_to_track:
        artist_id = artist_uri.split(':')[-1] # Get ID from URI
        try:
            results = sp.artist_albums(artist_id, album_type='album,single', limit=5, country='US') # Added country='US' to potentially improve results
            artist_info = sp.artist(artist_id)
            artist_name = artist_info.get('name', 'Unknown Artist')

            if results and results['items']:
                for item in results['items']:
                    release_id = item['id']
                    release_name = item['name']
                    release_type = item['album_type']
                    release_url = item['external_urls']['spotify']
                    release_date = item.get('release_date', 'N/A')
                    # Basic check: only consider releases added since the bot started
                    if release_id not in announced_release_ids:
                        print(f"✅ Found potential new release: {artist_name} - {release_name}")
                        message = (
                            f"🚨 **New {release_type.capitalize()} Release!** 🚨\n\n"
                            f"**Artist:** {artist_name}\n"
                            f"**Title:** {release_name}\n"
                            #f"**Released:** {release_date}\n" # Release date can be inaccurate sometimes, optional
                            f"🔗 Listen here: {release_url}"
                        )
                        try:
                            await channel.send(message)
                            announced_release_ids.add(release_id)
                            print(f"   Sent notification to channel {NOTIFICATION_CHANNEL_ID}.")
                            await asyncio.sleep(1) # Small delay between messages
                        except discord.errors.Forbidden:
                            print(f"   ❌ Error: Bot lacks permissions to send messages in channel {NOTIFICATION_CHANNEL_ID}.")
                        except Exception as send_e:
                            print(f"   ❌ Error sending message: {send_e}")


        except spotipy.exceptions.SpotifyException as se:
            print(f"   ❌ Spotify API Error checking artist {artist_uri}: {se}")
            # Handle specific errors like rate limiting if needed
            await asyncio.sleep(10) # Wait longer on API errors
        except Exception as e:
            print(f"   ❌ General Error checking artist {artist_uri}: {e}")
            await asyncio.sleep(5)

    print("Finished checking releases.")


@tasks.loop(hours=1) # Use tasks.loop decorator
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
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    if not background_check_loop.is_running():
        background_check_loop.start() # Start the background task using the decorator's controls

# --- Discord Commands ---

@bot.command(name='addartists', help='Adds one or more Spotify artist links/URIs to the tracking list.\nExample: !addartists <link1> <URI2> ...')
async def add_artists(ctx, *, artist_links: str):
    """Adds one or more Spotify artist links to the tracking list."""
    global artists_to_track_set
    if sp is None:
        await ctx.send("❌ Cannot add artists, Spotify connection is not available.")
        return

    added_artists_names = []
    failed_artists_input = []
    already_tracked_count = 0

    # Regex to find Spotify artist URLs or URIs more robustly
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1) # Group 1 captures the ID
        artist_uri = f"spotify:artist:{artist_id}"

        if artist_uri not in artists_to_track_set:
            try:
                # Verify the artist ID is valid by fetching info
                artist_info = sp.artist(artist_uri)
                artist_name = artist_info.get('name', f'ID:{artist_id}')
                artists_to_track_set.add(artist_uri)
                added_artists_names.append(artist_name)
                print(f"Added artist: {artist_name} ({artist_uri})")
            except spotipy.exceptions.SpotifyException as se:
                failed_artists_input.append(f"`{match.group(0)}` (Invalid ID or API Error: {se.http_status})")
                print(f"Failed to verify/add artist ID: {artist_id} - {se}")
            except Exception as e:
                failed_artists_input.append(f"`{match.group(0)}` (Unknown Error)")
                print(f"Failed to verify/add artist ID: {artist_id} - {e}")
        else:
            already_tracked_count += 1
            print(f"Artist already tracked: {artist_uri}")

    # --- Feedback Message ---
    if found_links_count == 0:
        await ctx.send("❌ No valid Spotify artist links or URIs found in your message. Use the format `https://open.spotify.com/playlist/5LA0xQetL5h7RXKjwBol031...` or `spotify:artist:ID...`")
        return

    response_message = ""
    if added_artists_names:
        response_message += f"✅ Added **{len(added_artists_names)}** artist(s) to track:\n- "
        response_message += "\n- ".join(added_artists_names)
        response_message += "\n\n"

    if already_tracked_count > 0:
        response_message += f"ℹ️ **{already_tracked_count}** artist(s) provided were already being tracked.\n\n"

    if failed_artists_input:
        response_message += f"⚠️ Failed to add or verify **{len(failed_artists_input)}** artist link(s)/URI(s):\n- "
        response_message += "\n- ".join(failed_artists_input)
        response_message += "\n"

    # Optional: Save the updated artists_to_track_set to a file here for persistence across restarts
    # Example: save_artists_to_file(artists_to_track_set)

    # Discord messages have a length limit (2000 chars), split if necessary
    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (message too long)"
    await ctx.send(response_message.strip())

@bot.command(name='listartists', help='Shows the list of artists currently being tracked.')
async def list_artists(ctx):
    """Lists the artists currently being tracked."""
    global artists_to_track_set
    if sp is None:
        await ctx.send("❌ Cannot list artists, Spotify connection is not available.")
        return

    if not artists_to_track_set:
        await ctx.send("ℹ️ No artists are currently being tracked. Use `!addartists <link>` to add some.")
        return

    artist_names = []
    failed_lookups = 0
    for uri in artists_to_track_set:
        try:
            artist_info = sp.artist(uri)
            artist_names.append(artist_info.get('name', f'Unknown Artist ({uri})'))
        except Exception as e:
            print(f"Error looking up artist name for {uri}: {e}")
            failed_lookups += 1
            artist_names.append(f"Error looking up ({uri})")
        await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits

    response_message = f"🎶 **Currently tracking {len(artists_to_track_set)} artist(s):**\n\n- "
    response_message += "\n- ".join(sorted(artist_names, key=str.lower)) # Sort alphabetically

    if failed_lookups > 0:
        response_message += f"\n\n⚠️ Could not retrieve names for {failed_lookups} tracked URIs (they might be invalid or there was an API error)."

    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (list too long)"
    await ctx.send(response_message)

@bot.command(name='removeartists', help='Removes one or more Spotify artist links/URIs from the tracking list.\nExample: !removeartists <link1> <URI2> ...')
async def remove_artists(ctx, *, artist_links: str):
    """Removes one or more Spotify artist links/URIs from the tracking list."""
    global artists_to_track_set
    removed_count = 0
    not_found_count = 0
    uris_to_remove = set()

    # Regex to find Spotify artist URLs or URIs
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1)
        artist_uri = f"spotify:artist:{artist_id}"
        uris_to_remove.add(artist_uri)

    if found_links_count == 0:
        await ctx.send("❌ No valid Spotify artist links or URIs found in your message.")
        return

    initial_set_size = len(artists_to_track_set)
    artists_to_track_set.difference_update(uris_to_remove) # Efficiently remove multiple items
    removed_count = initial_set_size - len(artists_to_track_set)
    not_found_count = len(uris_to_remove) - removed_count

    response_message = ""
    if removed_count > 0:
        response_message += f"✅ Removed **{removed_count}** artist(s) from the tracking list.\n"
    if not_found_count > 0:
        response_message += f"ℹ️ **{not_found_count}** provided artist(s) were not found in the tracking list.\n"
    if removed_count == 0 and not_found_count == len(uris_to_remove):
         response_message = "❌ None of the provided artists were found in the tracking list."

    # Optional: Save the updated artists_to_track_set to a file here for persistence

    await ctx.send(response_message.strip())


# --- Function to Start the Bot ---
def run_bot():
    if DISCORD_TOKEN is None:
        print("❌ Error: DISCORD_TOKEN environment variable not set.")
        return
    if sp is None:
        print("❌ Error: Spotify connection failed during initialization. Cannot start bot.")
        return

    try:
        print("Attempting to run bot...")
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("❌ Error: Improper token passed. Check your DISCORD_TOKEN.")
    except discord.HTTPException as http_e:
        print(f"❌ Discord HTTP Error: {http_e.status} {http_e.code} - {http_e.text}")
        if http_e.status == 429:
            print("   Rate limited by Discord. Try again later.")
    except Exception as e:
        print(f"❌ An unexpected error occurred while running the bot: {e}")