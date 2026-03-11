import os
from flask import Flask
from threading import Thread
import crypto_news_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Crypto News Bot is running!"

def run_bot():
    crypto_news_bot.main()

if __name__ == '__main__':
    # Start the bot in a background thread
    t = Thread(target=run_bot, daemon=True)
    t.start()
    
    # Get port from Render environment, default to 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

