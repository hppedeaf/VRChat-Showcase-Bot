"""
Combined server for the VRChat World Showcase Bot.
Runs both the Discord bot and web server.
"""
import asyncio
import threading
import os
import sys

# Add the bot directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from flask import Flask, request, jsonify, send_from_directory, Response
import main as bot_main
import config as config

# Initialize PostgreSQL when on Railway
if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("DATABASE_URL"):
    try:
        from database.pg_handler import setup_postgres_tables
        print("Initializing PostgreSQL database for Railway deployment...")
        setup_postgres_tables()
        print("PostgreSQL database initialized successfully.")
    except Exception as e:
        print(f"Error initializing PostgreSQL database: {e}")
        config.logger.error(f"Error initializing PostgreSQL database: {e}")

# Initialize Flask application
app = Flask(__name__, static_folder='web')

@app.route('/')
def index():
    """Serve the main website page."""
    return send_from_directory('web', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    """Serve static files from the web directory."""
    # Check if the file exists
    if os.path.exists(os.path.join('web', path)):
        return send_from_directory('web', path)
    else:
        # If not found, try to serve index.html
        return send_from_directory('web', 'index.html')

@app.route('/api/interactions', methods=['POST'])
def interactions():
    """Handle Discord interactions."""
    if request.method == 'POST':
        # Process Discord interaction
        return jsonify({"type": 1})  # Type 1 is PONG response
    return Response(status=400)

@app.route('/api/verify', methods=['GET', 'POST'])
def verify():
    """Handle role verification."""
    if request.method == 'GET':
        return jsonify({"message": "Verification endpoint is working"})
    elif request.method == 'POST':
        # Process verification
        return jsonify({"success": True})
    return Response(status=400)

@app.route('/api/status', methods=['GET'])
def status():
    """Return bot status information."""
    # Get status information
    guilds_count = getattr(bot_main, 'guild_count', 0)
    worlds_count = getattr(bot_main, 'worlds_count', 0)
    
    # Check database connection status
    db_status = "unknown"
    try:
        if os.getenv("DATABASE_URL"):
            # Check PostgreSQL connection
            from database.pg_handler import get_postgres_connection
            conn = get_postgres_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result and result[0] == 1:
                db_status = "connected (PostgreSQL)"
            conn.close()
        else:
            # Check SQLite connection
            import sqlite3
            conn = sqlite3.connect(config.DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result and result[0] == 1:
                db_status = "connected (SQLite)"
            conn.close()
    except Exception as e:
        db_status = f"error ({str(e)[:50]}...)" if len(str(e)) > 50 else f"error ({str(e)})"
    
    # Construct status response
    status_data = {
        "status": "online",
        "guilds": guilds_count,
        "worlds": worlds_count,
        "version": "1.0.0",
        "uptime": getattr(bot_main, 'uptime', 'Unknown'),
        "database": db_status,
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "local")
    }
    
    return jsonify(status_data)

def run_bot():
    """Run the Discord bot in a separate thread."""
    try:
        # Run the bot's main function
        asyncio.run(bot_main.main())
    except Exception as e:
        config.logger.error(f"Bot error: {e}")
        print(f"Bot error: {e}")

if __name__ == '__main__':
    # Start the bot in a background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Get the port from environment variable
    port = int(os.environ.get("PORT", 8080))
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=port)