import asyncio
import threading
import os
from flask import Flask, request, jsonify, send_from_directory
# Import your bot's main module
import bot.main as bot_main

app = Flask(__name__, static_folder='web')

@app.route('/')
def index():
    return send_from_directory('web', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('web', path)

@app.route('/api/interactions', methods=['POST'])
def interactions():
    # Handle Discord interactions
    return jsonify({"type": 1})

@app.route('/api/verify', methods=['GET', 'POST'])
def verify():
    # Handle role verification
    return jsonify({"success": True})

def run_bot():
    # Run your bot's main function
    asyncio.run(bot_main.main())

if __name__ == '__main__':
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Get the port from environment variable
    port = int(os.environ.get("PORT", 8080))
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=port)