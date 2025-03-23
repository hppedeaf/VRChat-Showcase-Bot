"""
Combined server for the VRChat World Showcase Bot.
Runs both the Discord bot and web dashboard with improved database handling.
"""
import asyncio
import threading
import os
import sys
import secrets
import logging

# Add the bot directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from flask import Flask, request, jsonify, send_from_directory, Response
from flask import render_template, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix
import main as bot_main
import config as config
from datetime import datetime
from database.pg_handler import add_missing_columns

# Initialize Flask application with correct static folder and template folder paths
current_dir = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_dir, 'web', 'static')
template_folder = os.path.join(current_dir, 'web', 'templates')

# Make sure static folder exists
os.makedirs(static_folder, exist_ok=True)

print(f"Current working directory: {os.getcwd()}")
print(f"Static folder path: {static_folder}")
print(f"Template folder path: {template_folder}")

# Make sure your app is properly configured
app = Flask(__name__, 
           static_folder=static_folder, 
           static_url_path='/static',
           template_folder=template_folder)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Set secret key for sessions - generate a new one on startup or use an env var
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))

# Custom error handler for 404 errors
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', message="Page not found. The requested page doesn't exist."), 404

# Custom error handler for 500 errors
@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', message="Internal server error. Please try again later."), 500

#########################################
# Template Filters
#########################################

@app.template_filter('now')
def filter_now(format_string):
    """Return the current time in the specified format."""
    return datetime.now().strftime(format_string)

@app.before_request
def before_request():
    print(f"Request path: {request.path}")
    
@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"500 error: {str(e)}")
    return render_template('error.html', message=f"Internal server error: {str(e)}"), 500

@app.errorhandler(404)
def page_not_found(e):
    app.logger.error(f"404 error: {request.path}")
    return render_template('error.html', message=f"Page not found: {request.path}"), 404

# Add more detailed logging
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    app.logger.setLevel(logging.DEBUG)
    
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
    try:
        # Get status information
        guilds_count = getattr(bot_main, 'guild_count', 0)
        worlds_count = getattr(bot_main, 'worlds_count', 0)
        
        # Get bot reference to check if it's running
        bot = getattr(bot_main, 'bot', None)
        is_online = bot is not None and bot.is_ready() if hasattr(bot, 'is_ready') else False
        
        # Get database status
        from database.db import check_postgres_availability
        pg_status = "online" if check_postgres_availability() else "offline"
        
        # Construct status response
        status_data = {
            "status": "online" if is_online else "offline",
            "guilds": guilds_count,
            "worlds": worlds_count,
            "database": pg_status,
            "version": "1.0.0",
            "uptime": getattr(bot_main, 'uptime', 'Unknown')
        }
        
        return jsonify(status_data)
    except Exception as e:
        app.logger.error(f"Error in status API: {e}")
        return jsonify({
            "status": "error",
            "message": "Could not retrieve bot status"
        }), 500

# Index route (root page)
@app.route('/')
def index():
    """Serve the landing page."""
    try:
        # If we have a marketing landing page, use it
        if os.path.exists(os.path.join(app.template_folder, 'marketing_index.html')):
            # Check if user is authenticated, redirect to dashboard if so
            if 'user_id' in session:
                return redirect(url_for('dashboard'))
            
            # Add bot_invite_url to context
            bot_invite_url = config.BOT_INVITE_URL
            return render_template('marketing_index.html', bot_invite_url=bot_invite_url)
        
        # Otherwise use our dashboard landing page
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return render_template('index.html')
    except Exception as e:
        app.logger.error(f"Error rendering index: {e}")
        return render_template('error.html', message=f"Template error: {str(e)}")

#########################################
# Database
#########################################

# Initialize database on first request
# Using a function that we'll register with app.before_first_request alternative
def initialize_db():
    """Set up the database and check if migration is needed"""
    from database.db import setup_database, check_postgres_availability
    
    # Set up the database
    try:
        setup_database()
        
        # Check if migration is needed (PostgreSQL is available and SQLite has data)
        if check_postgres_availability():
            app.logger.info("PostgreSQL is available, checking if migration is needed")
            from database.sync import check_migration_needed, migrate_sqlite_to_postgres
            
            if check_migration_needed():
                app.logger.info("Migration from SQLite to PostgreSQL is needed, starting migration")
                result = migrate_sqlite_to_postgres()
                if result.get("status") == "success":
                    app.logger.info(f"Migration completed successfully: {result.get('total')} records migrated")
                else:
                    app.logger.error(f"Migration failed: {result.get('message')}")
            else:
                app.logger.info("No migration needed, databases are in sync")
        else:
            app.logger.info("PostgreSQL is not available, using SQLite database")
            
    except Exception as e:
        app.logger.error(f"Database initialization error: {e}")

# Add API route to force migration
@app.route('/api/migrate-db', methods=['POST'])
def force_db_migration():
    """Force an immediate database migration from SQLite to PostgreSQL."""
    if request.method == 'POST':
        from database.sync import migrate_sqlite_to_postgres
        try:
            results = migrate_sqlite_to_postgres()
            
            return jsonify(results)
        except Exception as e:
            app.logger.error(f"Error in force migration: {e}")
            return jsonify({
                "status": "error",
                "message": f"Migration failed: {str(e)}"
            }), 500
    
    return Response(status=400)

#########################################
# Static Files and Direct Template Routes
#########################################

@app.route('/terms')
def terms():
    """Serve the terms of service page."""
    return render_template('terms.html', bot_invite_url=config.BOT_INVITE_URL)

@app.route('/privacy')
def privacy():
    """Serve the privacy policy page."""
    return render_template('privacy.html', bot_invite_url=config.BOT_INVITE_URL)

# Serve common static files at root level
@app.route('/favicon.ico')
def favicon():
    """Serve the favicon."""
    return send_from_directory(os.path.join(app.static_folder, 'img'), 'favicon.ico')

@app.route('/robots.txt')
def robots():
    """Serve robots.txt."""
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/styles.css')
def root_styles():
    """Serve styles.css at root level for direct references."""
    return send_from_directory(os.path.join(app.static_folder, 'css'), 'marketing-styles.css')

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
        # Add bot_invite_url to context
        bot_invite_url = config.BOT_INVITE_URL
        return render_template(template_path, bot_invite_url=bot_invite_url)
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
        # Set up the database before starting the bot
        from database.db import setup_database
        try:
            config.logger.info("Setting up database before starting bot...")
            setup_database()
            config.logger.info("Database setup completed successfully")
        except Exception as db_error:
            config.logger.error(f"Database setup error: {db_error}")
            # Continue anyway - the bot can still function with SQLite
        
        # Now run the bot
        asyncio.run(bot_main.main())
    except Exception as e:
        config.logger.error(f"Bot error: {e}")
        print(f"Bot error: {e}")

if __name__ == '__main__':
    # Create a logger for the Flask app
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    
    # Start the bot in a background thread
    app.logger.info("Starting Discord bot in background thread...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Import the web dashboard setup
    from web_dashboard import setup_routes
    
    # Set up the web dashboard routes
    # Pass app to setup_routes - bot will be grabbed from bot_main
    setup_routes(app)
    
    # Register the initialize_db function to be called on first request
    # This replaces the deprecated @app.before_first_request decorator
    with app.app_context():
        initialize_db()
    
    # Get the port from environment variable
    port = int(os.environ.get("PORT", 8080))
    
    # Whether to run in debug mode
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    print(f"Starting web server on port {port}, debug mode: {debug}")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=port, debug=debug)