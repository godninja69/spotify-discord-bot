from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
  return "Bot is alive!"

def run():
  # Get port from environment variable or default to 8080
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)

def keep_alive():
  '''
  Creates and starts a new thread that runs the Flask server.
  '''
  t = Thread(target=run)
  t.start()