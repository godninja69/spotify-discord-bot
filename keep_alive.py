from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
  # This endpoint needs to return a 200 OK status for UptimeRobot
  return "Bot is alive!"

def run():
  # Get port from environment variable Render provides, default to 8080 for local
  port = int(os.environ.get('PORT', 8080))
  # Host 0.0.0.0 is crucial for Render to reach the server inside the container
  print(f"--- Flask server attempting to run on host 0.0.0.0 port {port} ---") # DEBUG PRINT
  try:
    # Set use_reloader=False if you encounter issues with threads
    app.run(host='0.0.0.0', port=port) #, use_reloader=False)
    print("--- Flask server finished running (shouldn't happen unless stopped) ---") # DEBUG PRINT
  except Exception as e:
    print(f"!!! ERROR starting Flask server: {e}") # DEBUG PRINT

def keep_alive():
  '''
  Creates and starts a new thread that runs the Flask server.
  '''
  print("--- keep_alive function called, starting server thread ---") # DEBUG PRINT
  t = Thread(target=run)
  t.start()
  print("--- Server thread started ---") # DEBUG PRINT
