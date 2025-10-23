# main.py
print("--- main.py execution started ---") # ADD THIS VERY FIRST
import os
print("os imported.") # ADD THIS
try:
    from keep_alive import keep_alive
    print("keep_alive imported.") # ADD THIS
    import bot
    print("bot imported.") # ADD THIS
except ImportError as e:
    print(f"!!! IMPORT ERROR: {e}") # ADD THIS TO CATCH IMPORT FAILURES
    # Consider exiting if imports fail:
    # import sys
    # sys.exit(1)

print("Attempting to call keep_alive()...") # ADD THIS
keep_alive()
print("keep_alive() called. Background server thread should be starting.") # ADD THIS

print("Attempting to call bot.run_bot()...") # ADD THIS
try:
    bot.run_bot()
except Exception as e:
    print(f"!!! ERROR DURING bot.run_bot(): {e}") # ADD THIS

print("--- main.py finished (should not happen if bot runs forever) ---") # ADD THIS

from keep_alive import keep_alive
import bot # Imports the code from bot.py
import os

# --- Optional: Load .env file for local testing ---
# Make sure you have a .env file in the same directory
# with your secrets if you run this locally.
# DO NOT UPLOAD .env TO GITHUB
# from dotenv import load_dotenv
# load_dotenv()
# print("Attempting to load secrets from .env file for local testing...")
# print(f"Discord Token Loaded: {'Yes' if os.getenv('DISCORD_TOKEN') else 'No'}")
# print(f"Spotify Client ID Loaded: {'Yes' if os.getenv('SPOTIPY_CLIENT_ID') else 'No'}")
# print(f"Spotify Client Secret Loaded: {'Yes' if os.getenv('SPOTIPY_CLIENT_SECRET') else 'No'}")
# ----------------------------------------------------

# Start the Flask web server in a background thread
# This needs to run so Render can ping it and keep the bot alive
keep_alive()
print("Keep alive server started.")

# Start the Discord bot
print("Starting the Discord bot...")

bot.run_bot() # Calls the function from bot.py to start the bot
