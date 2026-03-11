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
    t = Thread(target=run_bot)
    t.start()
    
    # Start the Flask web server
    app.run(host='0.0.0.0', port=8080)
