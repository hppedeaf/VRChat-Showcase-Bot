"""
Combined server for the VRChat World Showcase Bot.
Runs both the Discord bot and web dashboard.
"""
import asyncio
import threading
import os
import sys
import secrets

# Add the bot directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from flask import Flask, request, jsonify, send_from_directory, Response
from flask import render_template, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix
import main as bot_main
import config as config
from datetime import datetime

# Initialize Flask application with correct static folder and template folder paths
current_dir = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_dir, 'web', 'static')
template_folder = os.path.join(current_dir, 'web', 'templates')

# Print paths for debugging
print(f"Static folder path: {static_folder}")
print(f"Template folder path: {template_folder}")

app = Flask(__name__, 
           static_folder=static_folder, 
           static_url_path='/static',
           template_folder=template_folder)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Set secret key for sessions - generate a new one on startup or use an env var
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))

# Import the web dashboard setup
from web_dashboard import setup_routes, user_guilds_cache

#########################################
# Template Filters
#########################################

@app.template_filter('now')
def filter_now(format_string):
    """Return the current time in the specified format."""
    return datetime.now().strftime(format_string)

#########################################
# API Routes
#########################################

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
    
    # Construct status response
    status_data = {
        "status": "online",
        "guilds": guilds_count,
        "worlds": worlds_count,
        "version": "1.0.0",
        "uptime": getattr(bot_main, 'uptime', 'Unknown')
    }
    
    return jsonify(status_data)

#########################################
# Static Files and Direct Template Routes
#########################################

@app.route('/terms')
def terms():
    """Serve the terms of service page."""
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    """Serve the privacy policy page."""
    return render_template('privacy.html')

# Fallback route to catch any undefined routes
@app.route('/<path:path>')
def catch_all(path):
    """
    Catch-all route to handle undefined paths.
    First tries to serve as static file, then checks for templates.
    """
    # First try to serve as a static file
    static_path = os.path.join(static_folder, path)
    if os.path.exists(static_path) and os.path.isfile(static_path):
        return send_from_directory(static_folder, path)
    
    # Then check if it's a template
    template_path = f"{path}.html"
    try:
        return render_template(template_path)
    except:
        # If not a template, pass to the next handler
        pass
    
    # Pass to the next route handler or return 404
    return render_template('error.html', message=f"Page not found: {path}"), 404

#########################################
# Bot Thread
#########################################

def run_bot():
    """Run the Discord bot in a separate thread."""
    try:
        # Store a reference to the bot for the web dashboard
        global bot
        # Run the bot's main function
        asyncio.run(bot_main.main())
    except Exception as e:
        config.logger.error(f"Bot error: {e}")
        print(f"Bot error: {e}")

if __name__ == '__main__':
    # Start the bot in a background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Set up the web dashboard routes
    # Debug bot guilds
    bot = getattr(bot_main, 'bot', None)
    if bot:
        print(f"Bot is in {len(bot.guilds)} guilds:")
        for guild in bot.guilds:
            print(f"- {guild.name} (ID: {guild.id})")
    else:
        print("Bot instance is None or not properly initialized")

    # Then pass bot to setup_routes
    setup_routes(app, bot)
    
    # Get the port from environment variable
    port = int(os.environ.get("PORT", 8080))
    
    # Whether to run in debug mode
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    print(f"Starting web server on port {port}, debug mode: {debug}")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=port, debug=debug)