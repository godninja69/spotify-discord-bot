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
NOTIFICATION_CHANNEL_ID = 1430238059533832352 # Use the actual ID here

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
    """Adds one or more Spotify artist links to the tracking list."""
    global artists_to_track_set
    if sp is None:
        await ctx.send("❌ Cannot add artists, Spotify connection is not available.")
        return

    added_artists_names = []
    failed_artists_input = []
    already_tracked_count = 0

    # Regex to find Spotify artist URLs or URIs more robustly
    # Looks for the 22-character base-62 ID
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1) # Group 1 captures the ID
        artist_uri = f"spotify:artist:{artist_id}"
        original_input = match.group(0) # Store the original link/URI text for error messages

        if artist_uri not in artists_to_track_set:
            try:
                # Verify the artist ID is valid by fetching info
                print(f"Attempting to verify artist URI: {artist_uri}")
                artist_info = sp.artist(artist_uri) # This is the API call that might fail
                artist_name = artist_info.get('name', f'ID:{artist_id}')
                artists_to_track_set.add(artist_uri)
                added_artists_names.append(artist_name)
                print(f"✅ Successfully added artist: {artist_name} ({artist_uri})")

            # --- MORE SPECIFIC ERROR CATCHING ---
            except spotipy.exceptions.SpotifyException as se:
                # Provides Spotify's error message, status code, and reason
                error_details = f"Spotify API Error (Status: {se.http_status}, Code: {se.code}, Reason: {se.msg})"
                failed_artists_input.append(f"`{original_input}` ({error_details})")
                print(f"❌ Failed to verify/add {artist_uri} - {error_details}")
            except Exception as e:
                # Catches any other error (network issues, unexpected responses, etc.)
                error_type = type(e).__name__
                failed_artists_input.append(f"`{original_input}` (Error Type: {error_type})")
                print(f"❌ Failed to verify/add {artist_uri} - An unexpected error occurred: {error_type} - {e}")
                # Print the full traceback to logs for detailed debugging:
                print("Full Traceback:") # Keep this print
                traceback.print_exc() # *** THIS LINE IS NOW UNCOMMENTED ***
            # ------------------------------------

        else:
            already_tracked_count += 1
            print(f"ℹ️ Artist already tracked: {artist_uri}")

        await asyncio.sleep(0.1) # Small delay between checking each artist

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
        response_message += f"ℹ️ **{already_tracked_count}** provided artist(s) were already being tracked.\n\n"

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
    # Send feedback that it might take a moment
    initial_message = await ctx.send(f"⏳ Fetching names for {len(artists_to_track_set)} tracked artists...")

    for uri in artists_to_track_set:
        try:
            artist_info = sp.artist(uri)
            artist_names.append(artist_info.get('name', f'Unknown Artist ({uri})'))
        except Exception as e:
            print(f"Error looking up artist name for {uri}: {e}")
            failed_lookups += 1
            artist_names.append(f"Error looking up (`{uri.split(':')[-1]}`)")
        await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits

    response_message = f"🎶 **Currently tracking {len(artists_to_track_set)} artist(s):**\n\n- "
    response_message += "\n- ".join(sorted(artist_names, key=str.lower)) # Sort alphabetically

    if failed_lookups > 0:
        response_message += f"\n\n⚠️ Could not retrieve names for {failed_lookups} tracked URIs (they might be invalid or there was an API error)."

    # Edit the initial message or send a new one if too long
    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (list too long)"
        await initial_message.edit(content=response_message)
    else:
        try:
            await initial_message.edit(content=response_message)
        except discord.errors.NotFound: # Handle if the original message was deleted
            await ctx.send(response_message)
        except Exception as e:
            print(f"Error editing message for listartists: {e}")
            await ctx.send(response_message) # Send as new on other errors


@bot.command(name='removeartists', help='Removes one or more Spotify artist links/URIs from the tracking list.\nExample: !removeartists <link1> <URI2> ...')
async def remove_artists(ctx, *, artist_links: str):
    """Removes one or more Spotify artist links/URIs from the tracking list."""
    global artists_to_track_set
    removed_count = 0
    not_found_count = 0
    uris_to_remove = set()
    removed_names = [] # Store names for feedback
    original_input_map = {} # Map URI back to original input for error messages

    # Regex to find Spotify artist URLs or URIs
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1)
        artist_uri = f"spotify:artist:{artist_id}"
        uris_to_remove.add(artist_uri)
        original_input_map[artist_uri] = match.group(0) # Store original input

    if found_links_count == 0:
        await ctx.send("❌ No valid Spotify artist links or URIs found in your message.")
        return

    removed_uris = []
    failed_to_find_inputs = [] # Store original inputs of those not found
    # Check which ones are actually in the set before removing
    for uri in uris_to_remove:
        if uri in artists_to_track_set:
            removed_uris.append(uri)
            artists_to_track_set.remove(uri) # Remove it
        else:
            failed_to_find_inputs.append(f"`{original_input_map.get(uri, uri)}`")

    removed_count = len(removed_uris)
    not_found_count = len(failed_to_find_inputs)

    # Try to get names for removed artists (optional, adds API calls)
    if sp and removed_uris:
        for uri in removed_uris:
             try:
                 artist_info = sp.artist(uri)
                 removed_names.append(artist_info.get('name', f'`{uri.split(":")[-1]}`'))
                 await asyncio.sleep(0.1) # Avoid rate limit
             except Exception:
                 removed_names.append(f"Error getting name (`{uri.split(':')[-1]}`)")


    response_message = ""
    if removed_count > 0:
        names_str = ", ".join(removed_names) if removed_names else f"{removed_count} artist(s)"
        response_message += f"✅ Removed **{names_str}** from the tracking list.\n"
    if not_found_count > 0:
        response_message += f"ℹ️ **{not_found_count}** provided artist(s) were not found in the tracking list: {', '.join(failed_to_find_inputs)}\n"
    if removed_count == 0 and not_found_count > 0 :
         response_message = "❌ None of the provided artists were found in the tracking list."
    elif removed_count == 0 and not_found_count == 0: # Should not happen if found_links_count > 0
        response_message = "No artists were removed."

    # Optional: Save the updated artists_to_track_set to a file here for persistence

    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (message too long)"
    await ctx.send(response_message.strip())


# --- Function to Start the Bot ---
def run_bot():
    """Validates required variables and starts the bot."""
    print("--- Inside run_bot function ---")
    if DISCORD_TOKEN is None:
        print("❌ CRITICAL: DISCORD_TOKEN environment variable not set. Bot cannot start.")
        return # Stop here if no token
    if sp is None:
        print("❌ CRITICAL: Spotify connection failed during initialization. Bot cannot start.")
        return # Stop here if Spotify failed

    print(f"Attempting bot.run() with token ending in ...{DISCORD_TOKEN[-6:]}")

    try:
        # This is the line that connects to Discord and runs the bot
        bot.run(DISCORD_TOKEN)

    # Specific check for login failure (wrong token)
    except discord.errors.LoginFailure:
        print("❌❌❌ LOGIN FAILURE: Improper token passed. Check your DISCORD_TOKEN in Render Environment variables.")

    # Specific check for missing intents
    except discord.errors.PrivilegedIntentsRequired as intent_error:
        # Try to get shard_id, might be None
        shard_id = getattr(intent_error, 'shard_id', 'Unknown')
        print(f"❌❌❌ INTENT ERROR: The bot is missing required privileged intents (Shard ID: {shard_id}).")
        print("   Please ensure MESSAGE CONTENT INTENT (and any others needed) are enabled in the Discord Developer Portal.")

    # Catch network or connection issues
    except discord.errors.ConnectionClosed as conn_error:
         print(f"❌❌❌ CONNECTION ERROR: Discord connection closed unexpectedly: Code {conn_error.code}, Reason: {conn_error.reason}")

    # Catch generic Discord HTTP errors (like rate limits)
    except discord.HTTPException as http_e:
        print(f"❌❌❌ Discord HTTP Error: Status {http_e.status}, Code {http_e.code}")
        print(f"   Response Text: {http_e.text}")
        if http_e.status == 429:
            print("   >>> Rate limited by Discord. Waiting before attempting restart might be needed. <<<")

    # Catch ANY other unexpected error during bot execution
    except Exception as e:
        print(f"❌❌❌ UNEXPECTED ERROR during bot.run(): {type(e).__name__} - {e}")
        print("Full Traceback:")
        traceback.print_exc() # Prints the detailed error location

    finally:
         print("--- bot.run() has exited. The bot process has stopped. ---") # This will print if the bot stops

# Note: The code to actually *run* the bot is in main.py
# This file defines the bot and its functions.

# Example Persistence Functions (Uncomment and modify if you want persistence)
# import json
# ARTIST_FILE = 'tracked_artists.json' # Store file in the root directory

# def load_artists_from_file():
#     """Loads artist URIs from a JSON file."""
#     default_set = set() # Start empty if file doesn't exist
#     try:
#         with open(ARTIST_FILE, 'r') as f:
#             # Load list from file and convert to set
#             artist_list = json.load(f)
#             if isinstance(artist_list, list):
#                 return set(artist_list)
#             else:
#                 print(f"Warning: '{ARTIST_FILE}' does not contain a valid list. Starting empty.")
#                 return default_set
#     except FileNotFoundError:
#         print(f"'{ARTIST_FILE}' not found. Starting with empty artist list.")
#         return default_set
#     except json.JSONDecodeError:
#         print(f"Error decoding JSON from '{ARTIST_FILE}'. Starting empty.")
#         return default_set
#     except Exception as e:
#         print(f"Error loading artists from file: {e}")
#         return default_set

# def save_artists_to_file(artist_set):
#     """Saves artist URIs to a JSON file."""
#     try:
#         # Convert set to list before saving to JSON
#         with open(ARTIST_FILE, 'w') as f:
#             json.dump(list(artist_set), f, indent=4)
#         print(f"Saved {len(artist_set)} artists to '{ARTIST_FILE}'")
#     except Exception as e:
#         print(f"Error saving artists to file: {e}")

# --- Load artists at startup if using persistence ---
# You would uncomment these lines if you add the load/save functions
# print("Loading tracked artists from file...")
# artists_to_track_set = load_artists_from_file()
# print(f"Loaded {len(artists_to_track_set)} artists.")
# --------------------------------------------------import discord
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
    """Adds one or more Spotify artist links to the tracking list."""
    global artists_to_track_set
    if sp is None:
        await ctx.send("❌ Cannot add artists, Spotify connection is not available.")
        return

    added_artists_names = []
    failed_artists_input = []
    already_tracked_count = 0

    # Regex to find Spotify artist URLs or URIs more robustly
    # Looks for the 22-character base-62 ID
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1) # Group 1 captures the ID
        artist_uri = f"spotify:artist:{artist_id}"
        original_input = match.group(0) # Store the original link/URI text for error messages

        if artist_uri not in artists_to_track_set:
            try:
                # Verify the artist ID is valid by fetching info
                print(f"Attempting to verify artist URI: {artist_uri}")
                artist_info = sp.artist(artist_uri) # This is the API call that might fail
                artist_name = artist_info.get('name', f'ID:{artist_id}')
                artists_to_track_set.add(artist_uri)
                added_artists_names.append(artist_name)
                print(f"✅ Successfully added artist: {artist_name} ({artist_uri})")

            # --- MORE SPECIFIC ERROR CATCHING ---
            except spotipy.exceptions.SpotifyException as se:
                # Provides Spotify's error message, status code, and reason
                error_details = f"Spotify API Error (Status: {se.http_status}, Code: {se.code}, Reason: {se.msg})"
                failed_artists_input.append(f"`{original_input}` ({error_details})")
                print(f"❌ Failed to verify/add {artist_uri} - {error_details}")
            except Exception as e:
                # Catches any other error (network issues, unexpected responses, etc.)
                error_type = type(e).__name__
                failed_artists_input.append(f"`{original_input}` (Error Type: {error_type})")
                print(f"❌ Failed to verify/add {artist_uri} - An unexpected error occurred: {error_type} - {e}")
                # Print the full traceback to logs for detailed debugging:
                print("Full Traceback:") # Keep this print
                traceback.print_exc() # *** THIS LINE IS NOW UNCOMMENTED ***
            # ------------------------------------

        else:
            already_tracked_count += 1
            print(f"ℹ️ Artist already tracked: {artist_uri}")

        await asyncio.sleep(0.1) # Small delay between checking each artist

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
        response_message += f"ℹ️ **{already_tracked_count}** provided artist(s) were already being tracked.\n\n"

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
    # Send feedback that it might take a moment
    initial_message = await ctx.send(f"⏳ Fetching names for {len(artists_to_track_set)} tracked artists...")

    for uri in artists_to_track_set:
        try:
            artist_info = sp.artist(uri)
            artist_names.append(artist_info.get('name', f'Unknown Artist ({uri})'))
        except Exception as e:
            print(f"Error looking up artist name for {uri}: {e}")
            failed_lookups += 1
            artist_names.append(f"Error looking up (`{uri.split(':')[-1]}`)")
        await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits

    response_message = f"🎶 **Currently tracking {len(artists_to_track_set)} artist(s):**\n\n- "
    response_message += "\n- ".join(sorted(artist_names, key=str.lower)) # Sort alphabetically

    if failed_lookups > 0:
        response_message += f"\n\n⚠️ Could not retrieve names for {failed_lookups} tracked URIs (they might be invalid or there was an API error)."

    # Edit the initial message or send a new one if too long
    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (list too long)"
        await initial_message.edit(content=response_message)
    else:
        try:
            await initial_message.edit(content=response_message)
        except discord.errors.NotFound: # Handle if the original message was deleted
            await ctx.send(response_message)
        except Exception as e:
            print(f"Error editing message for listartists: {e}")
            await ctx.send(response_message) # Send as new on other errors


@bot.command(name='removeartists', help='Removes one or more Spotify artist links/URIs from the tracking list.\nExample: !removeartists <link1> <URI2> ...')
async def remove_artists(ctx, *, artist_links: str):
    """Removes one or more Spotify artist links/URIs from the tracking list."""
    global artists_to_track_set
    removed_count = 0
    not_found_count = 0
    uris_to_remove = set()
    removed_names = [] # Store names for feedback
    original_input_map = {} # Map URI back to original input for error messages

    # Regex to find Spotify artist URLs or URIs
    spotify_link_pattern = re.compile(r'(?:https?://open\.spotify\.com/artist/|spotify:artist:)([a-zA-Z0-9]{22})')

    matches = spotify_link_pattern.finditer(artist_links)
    found_links_count = 0

    for match in matches:
        found_links_count += 1
        artist_id = match.group(1)
        artist_uri = f"spotify:artist:{artist_id}"
        uris_to_remove.add(artist_uri)
        original_input_map[artist_uri] = match.group(0) # Store original input

    if found_links_count == 0:
        await ctx.send("❌ No valid Spotify artist links or URIs found in your message.")
        return

    removed_uris = []
    failed_to_find_inputs = [] # Store original inputs of those not found
    # Check which ones are actually in the set before removing
    for uri in uris_to_remove:
        if uri in artists_to_track_set:
            removed_uris.append(uri)
            artists_to_track_set.remove(uri) # Remove it
        else:
            failed_to_find_inputs.append(f"`{original_input_map.get(uri, uri)}`")

    removed_count = len(removed_uris)
    not_found_count = len(failed_to_find_inputs)

    # Try to get names for removed artists (optional, adds API calls)
    if sp and removed_uris:
        for uri in removed_uris:
             try:
                 artist_info = sp.artist(uri)
                 removed_names.append(artist_info.get('name', f'`{uri.split(":")[-1]}`'))
                 await asyncio.sleep(0.1) # Avoid rate limit
             except Exception:
                 removed_names.append(f"Error getting name (`{uri.split(':')[-1]}`)")


    response_message = ""
    if removed_count > 0:
        names_str = ", ".join(removed_names) if removed_names else f"{removed_count} artist(s)"
        response_message += f"✅ Removed **{names_str}** from the tracking list.\n"
    if not_found_count > 0:
        response_message += f"ℹ️ **{not_found_count}** provided artist(s) were not found in the tracking list: {', '.join(failed_to_find_inputs)}\n"
    if removed_count == 0 and not_found_count > 0 :
         response_message = "❌ None of the provided artists were found in the tracking list."
    elif removed_count == 0 and not_found_count == 0: # Should not happen if found_links_count > 0
        response_message = "No artists were removed."

    # Optional: Save the updated artists_to_track_set to a file here for persistence

    if len(response_message) > 1950:
        response_message = response_message[:1950] + "... (message too long)"
    await ctx.send(response_message.strip())


# --- Function to Start the Bot ---
def run_bot():
    """Validates required variables and starts the bot."""
    print("--- Inside run_bot function ---")
    if DISCORD_TOKEN is None:
        print("❌ CRITICAL: DISCORD_TOKEN environment variable not set. Bot cannot start.")
        return # Stop here if no token
    if sp is None:
        print("❌ CRITICAL: Spotify connection failed during initialization. Bot cannot start.")
        return # Stop here if Spotify failed

    print(f"Attempting bot.run() with token ending in ...{DISCORD_TOKEN[-6:]}")

    try:
        # This is the line that connects to Discord and runs the bot
        bot.run(DISCORD_TOKEN)

    # Specific check for login failure (wrong token)
    except discord.errors.LoginFailure:
        print("❌❌❌ LOGIN FAILURE: Improper token passed. Check your DISCORD_TOKEN in Render Environment variables.")

    # Specific check for missing intents
    except discord.errors.PrivilegedIntentsRequired as intent_error:
        # Try to get shard_id, might be None
        shard_id = getattr(intent_error, 'shard_id', 'Unknown')
        print(f"❌❌❌ INTENT ERROR: The bot is missing required privileged intents (Shard ID: {shard_id}).")
        print("   Please ensure MESSAGE CONTENT INTENT (and any others needed) are enabled in the Discord Developer Portal.")

    # Catch network or connection issues
    except discord.errors.ConnectionClosed as conn_error:
         print(f"❌❌❌ CONNECTION ERROR: Discord connection closed unexpectedly: Code {conn_error.code}, Reason: {conn_error.reason}")

    # Catch generic Discord HTTP errors (like rate limits)
    except discord.HTTPException as http_e:
        print(f"❌❌❌ Discord HTTP Error: Status {http_e.status}, Code {http_e.code}")
        print(f"   Response Text: {http_e.text}")
        if http_e.status == 429:
            print("   >>> Rate limited by Discord. Waiting before attempting restart might be needed. <<<")

    # Catch ANY other unexpected error during bot execution
    except Exception as e:
        print(f"❌❌❌ UNEXPECTED ERROR during bot.run(): {type(e).__name__} - {e}")
        print("Full Traceback:")
        traceback.print_exc() # Prints the detailed error location

    finally:
         print("--- bot.run() has exited. The bot process has stopped. ---") # This will print if the bot stops

# Note: The code to actually *run* the bot is in main.py
# This file defines the bot and its functions.

# Example Persistence Functions (Uncomment and modify if you want persistence)
# import json
# ARTIST_FILE = 'tracked_artists.json' # Store file in the root directory

# def load_artists_from_file():
#     """Loads artist URIs from a JSON file."""
#     default_set = set() # Start empty if file doesn't exist
#     try:
#         with open(ARTIST_FILE, 'r') as f:
#             # Load list from file and convert to set
#             artist_list = json.load(f)
#             if isinstance(artist_list, list):
#                 return set(artist_list)
#             else:
#                 print(f"Warning: '{ARTIST_FILE}' does not contain a valid list. Starting empty.")
#                 return default_set
#     except FileNotFoundError:
#         print(f"'{ARTIST_FILE}' not found. Starting with empty artist list.")
#         return default_set
#     except json.JSONDecodeError:
#         print(f"Error decoding JSON from '{ARTIST_FILE}'. Starting empty.")
#         return default_set
#     except Exception as e:
#         print(f"Error loading artists from file: {e}")
#         return default_set

# def save_artists_to_file(artist_set):
#     """Saves artist URIs to a JSON file."""
#     try:
#         # Convert set to list before saving to JSON
#         with open(ARTIST_FILE, 'w') as f:
#             json.dump(list(artist_set), f, indent=4)
#         print(f"Saved {len(artist_set)} artists to '{ARTIST_FILE}'")
#     except Exception as e:
#         print(f"Error saving artists to file: {e}")

# --- Load artists at startup if using persistence ---
# You would uncomment these lines if you add the load/save functions
# print("Loading tracked artists from file...")
# artists_to_track_set = load_artists_from_file()
# print(f"Loaded {len(artists_to_track_set)} artists.")
# --------------------------------------------------
