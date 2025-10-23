print("--- main.py execution started ---") # DEBUG PRINT
import os
print("os imported.") # DEBUG PRINT
bot = None # Initialize bot to None
keep_alive = None # Initialize keep_alive to None

try:
    from keep_alive import keep_alive
    print("keep_alive imported successfully.") # DEBUG PRINT
    import bot # Assuming your main bot logic is in bot.py
    print("bot imported successfully.") # DEBUG PRINT
except ImportError as e:
    print(f"!!! IMPORT ERROR: {e}") # DEBUG PRINT - Crucial to see if files are found
    # Optional: Exit if essential imports fail
    # import sys
    # sys.exit(f"Stopping due to import error: {e}")
except Exception as e:
    print(f"!!! UNEXPECTED ERROR during import: {e}") # DEBUG PRINT

# Check if imports were successful before proceeding
if keep_alive is None:
    print("!!! keep_alive function was not imported. Cannot start web server.")
if bot is None:
    print("!!! bot module was not imported. Cannot start Discord bot.")

if keep_alive and bot: # Only proceed if both imports worked
    print("Attempting to call keep_alive()...") # DEBUG PRINT
    keep_alive()
    print("keep_alive() called. Background server thread should be starting.") # DEBUG PRINT

    print("Attempting to call bot.run_bot()...") # DEBUG PRINT
    try:
        bot.run_bot() # Calls the function from bot.py to start the bot
    except Exception as e:
        print(f"!!! ERROR DURING bot.run_bot() CALL: {e}") # DEBUG PRINT

else:
    print("!!! Skipping keep_alive() and bot.run_bot() due to import errors.")

print("--- main.py reached end (this should ideally not happen if bot runs forever) ---") # DEBUG PRINT
