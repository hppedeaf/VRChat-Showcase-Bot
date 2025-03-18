"""
Web dashboard integration for the VRChat World Showcase Bot.
This module handles the integration between the Flask web server and Discord bot.
"""
import os
import json
import requests
from datetime import datetime
from flask import render_template, redirect, url_for, session, request, flash, jsonify
from database.models import ServerChannels, WorldPosts, ServerTags
import config as config  # Import the config module
import main as bot_main  # Import the bot main module to access the bot instance

# Constants from config
DISCORD_CLIENT_ID = getattr(config, 'DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = getattr(config, 'DISCORD_CLIENT_SECRET', '')
DISCORD_REDIRECT_URI = getattr(config, 'DISCORD_REDIRECT_URI', '')
BOT_INVITE_URL = getattr(config, 'BOT_INVITE_URL', '')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'
OAUTH_SCOPES = ['identify', 'guilds']

# User guilds cache for faster access
user_guilds_cache = {}

def setup_routes(app):
    """
    Set up all web dashboard routes.
    
    Args:
        app: Flask application instance
    """
    # Add logging for debugging
    app.logger.info("Setting up web dashboard routes")
    
    # Try to get bot instance
    bot = getattr(bot_main, 'bot', None)
    if bot:
        app.logger.info(f"Bot is available: {bot}")
    else:
        app.logger.warning("Bot instance not available for web dashboard")
    
    @app.context_processor
    def inject_globals():
        """Add global variables to all templates."""
        return {
            'discord_client_id': DISCORD_CLIENT_ID,
            'bot_name': getattr(config, 'DASHBOARD_TITLE', 'VRChat World Showcase'),
            'current_year': datetime.now().year,
            'bot_invite_url': BOT_INVITE_URL
        }
    
    @app.route('/login')
    def login():
        """Redirect to Discord OAuth2 login."""
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            return render_template('error.html', 
                                 message="Discord OAuth2 credentials are not configured. Please set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET environment variables.")
        
        params = {
            'client_id': DISCORD_CLIENT_ID,
            'redirect_uri': DISCORD_REDIRECT_URI,
            'response_type': 'code',
            'scope': ' '.join(OAUTH_SCOPES)
        }
        
        auth_url = f"{DISCORD_API_ENDPOINT}/oauth2/authorize?{encode_params(params)}"
        return redirect(auth_url)
    
    @app.route('/callback')
    def callback():
        """Handle Discord OAuth2 callback."""
        error = request.args.get('error')
        if error:
            return render_template('error.html', message=f"Discord OAuth2 error: {error}")
        
        code = request.args.get('code')
        if not code:
            return render_template('error.html', message="No authorization code received")
        
        # Exchange code for token
        token_data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DISCORD_REDIRECT_URI,
            'scope': ' '.join(OAUTH_SCOPES)
        }
        
        try:
            token_response = requests.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=token_data)
            token_response.raise_for_status()
            token_json = token_response.json()
            
            access_token = token_json['access_token']
            
            # Get user info
            headers = {'Authorization': f"Bearer {access_token}"}
            user_response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=headers)
            user_response.raise_for_status()
            user_json = user_response.json()
            
            session['user_id'] = user_json['id']
            session['username'] = user_json['username']
            session['avatar'] = user_json.get('avatar')
            session['access_token'] = access_token
            
            # Get user's guilds
            guilds_response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
            guilds_response.raise_for_status()
            guilds_json = guilds_response.json()
            
            # Cache the user's guilds
            user_guilds_cache[user_json['id']] = guilds_json
            
            return redirect(url_for('dashboard'))
            
        except requests.RequestException as e:
            app.logger.error(f"Error during OAuth: {str(e)}")
            return render_template('error.html', message=f"Error authenticating with Discord: {str(e)}")
    
    @app.route('/dashboard')
    def dashboard():
        """User dashboard showing servers they can manage."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user_id = session['user_id']
        user_guilds = user_guilds_cache.get(user_id, [])
        
        # Filter to only guilds where the user has admin permissions
        admin_guilds = [g for g in user_guilds if has_admin_permission(g)]
        
        # Check which guilds are using the bot
        bot_guilds = []
        bot_guild_ids = []
        
        if bot:
            try:
                bot_guild_ids = [str(g.id) for g in bot.guilds]
                app.logger.info(f"Bot is in {len(bot_guild_ids)} guilds")
            except Exception as e:
                app.logger.error(f"Error accessing bot guilds: {e}")
        
        try:
            # For each admin guild, check if the bot is in it
            for guild in admin_guilds:
                guild_id = guild['id']
                is_using_bot = guild_id in bot_guild_ids
                
                # Check if the guild has configured the bot
                has_configured = False
                if is_using_bot:
                    try:
                        forum_config = ServerChannels.get_forum_channel(int(guild_id))
                        has_configured = forum_config is not None
                    except Exception as db_error:
                        app.logger.error(f"Database error checking configuration: {db_error}")
                
                bot_guilds.append({
                    'id': guild_id,
                    'name': guild['name'],
                    'icon': guild['icon'],
                    'is_using_bot': is_using_bot,
                    'has_configured': has_configured
                })
        except Exception as e:
            app.logger.error(f"Error fetching guild information: {e}")
            flash(f"Error fetching guild information: {str(e)}", "error")
        
        return render_template('dashboard.html', 
                              user=session, 
                              guilds=bot_guilds,
                              bot_invite_url=BOT_INVITE_URL)
    
    @app.route('/force-refresh-guilds', methods=['GET'])
    def force_refresh_guilds():
        """Force refresh of guild information."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user_id = session['user_id']
        # Clear the cache
        if user_id in user_guilds_cache:
            del user_guilds_cache[user_id]
            
        # Force re-fetch from Discord API
        if 'access_token' in session:
            try:
                headers = {'Authorization': f"Bearer {session['access_token']}"}
                guilds_response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
                guilds_response.raise_for_status()
                guilds_json = guilds_response.json()
                
                # Update cache
                user_guilds_cache[user_id] = guilds_json
                flash("Successfully refreshed server information", "success")
            except Exception as e:
                flash(f"Error refreshing: {str(e)}", "error")
        
        return redirect(url_for('dashboard'))

    @app.route('/guild/<guild_id>')
    def guild_dashboard(guild_id):
        """Dashboard for a specific guild."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            flash("You don't have administrator permission for this server.", "error")
            return redirect(url_for('dashboard'))
        
        guild_id = int(guild_id)  # Convert to int for database queries
        
        # Get guild information from cache
        user_id = session['user_id']
        user_guilds = user_guilds_cache.get(user_id, [])
        guild_info = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
        
        if not guild_info:
            flash("Server not found", "error")
            return redirect(url_for('dashboard'))
        
        # Get guild configuration
        forum_config = None
        try:
            forum_config = ServerChannels.get_forum_channel(guild_id)
        except Exception as e:
            app.logger.error(f"Error fetching forum configuration: {e}")
        
        # Get stats
        world_count = 0
        tag_count = 0
        
        try:
            # Count worlds
            world_posts = WorldPosts.get_all_posts(guild_id)
            world_count = len(world_posts)
            
            # Count tags
            server_tags = ServerTags.get_all_tags(guild_id)
            tag_count = len(server_tags)
        except Exception as e:
            app.logger.error(f"Error fetching server data: {e}")
            flash(f"Error fetching server data: {str(e)}", "error")
        
        return render_template('guild_dashboard.html',
                              user=session,
                              guild=guild_info,
                              forum_config=forum_config,
                              world_count=world_count,
                              tag_count=tag_count)
    
    @app.route('/guild/<guild_id>/worlds')
    def guild_worlds(guild_id):
        """View all worlds for a specific guild."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            flash("You don't have administrator permission for this server.", "error")
            return redirect(url_for('dashboard'))
        
        guild_id = int(guild_id)
        
        # Get guild information
        user_id = session['user_id']
        user_guilds = user_guilds_cache.get(user_id, [])
        guild_info = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
        
        # Get worlds
        worlds = []
        try:
            world_posts = WorldPosts.get_all_posts(guild_id)
            worlds = sorted(world_posts, key=lambda w: w.get('thread_id', 0), reverse=True)
        except Exception as e:
            app.logger.error(f"Error fetching worlds: {e}")
            flash(f"Error fetching worlds: {str(e)}", "error")
        
        return render_template('guild_worlds.html',
                              user=session,
                              guild=guild_info,
                              worlds=worlds)
    
    @app.route('/guild/<guild_id>/tags')
    def guild_tags(guild_id):
        """View and manage tags for a specific guild."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            flash("You don't have administrator permission for this server.", "error")
            return redirect(url_for('dashboard'))
        
        guild_id = int(guild_id)
        
        # Get guild information
        user_id = session['user_id']
        user_guilds = user_guilds_cache.get(user_id, [])
        guild_info = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
        
        # Get tags
        tags = []
        try:
            server_tags = ServerTags.get_all_tags(guild_id)
            tags = sorted(server_tags, key=lambda t: t.get('tag_name', '').lower())
        except Exception as e:
            app.logger.error(f"Error fetching tags: {e}")
            flash(f"Error fetching tags: {str(e)}", "error")
        
        return render_template('guild_tags.html',
                              user=session,
                              guild=guild_info,
                              tags=tags)
    
    @app.route('/guild/<guild_id>/settings')
    def guild_settings(guild_id):
        """Settings for a specific guild."""
        if 'user_id' not in session:
            return redirect(url_for('login'))
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            flash("You don't have administrator permission for this server.", "error")
            return redirect(url_for('dashboard'))
        
        guild_id = int(guild_id)
        
        # Get guild information
        user_id = session['user_id']
        user_guilds = user_guilds_cache.get(user_id, [])
        guild_info = next((g for g in user_guilds if g['id'] == str(guild_id)), None)
        
        # Get settings
        forum_config = None
        try:
            forum_config = ServerChannels.get_forum_channel(guild_id)
        except Exception as e:
            app.logger.error(f"Error fetching forum configuration: {e}")
        
        return render_template('guild_settings.html',
                              user=session,
                              guild=guild_info,
                              forum_config=forum_config)
    
    @app.route('/logout')
    def logout():
        """Log the user out."""
        user_id = session.get('user_id')
        if user_id and user_id in user_guilds_cache:
            del user_guilds_cache[user_id]
        
        session.clear()
        return redirect(url_for('index'))

    # API Endpoints for the dashboard
    
    @app.route('/api/guild/<guild_id>/reset-config', methods=['POST'])
    def api_reset_config(guild_id):
        """API endpoint to reset a guild's configuration."""
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Not authenticated"}), 401
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            return jsonify({"success": False, "message": "Permission denied"}), 403
        
        try:
            guild_id = int(guild_id)
            ServerChannels.clear_forum_channel(guild_id)
            return jsonify({"success": True})
        except Exception as e:
            app.logger.error(f"Error resetting config: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
    
    @app.route('/api/guild/<guild_id>/scan', methods=['POST'])
    def api_scan_guild(guild_id):
        """API endpoint to trigger a guild scan."""
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Not authenticated"}), 401
            
        # Check permission
        if not check_guild_permission(session['user_id'], guild_id):
            return jsonify({"success": False, "message": "Permission denied"}), 403
        
        # For now, just return a message to use Discord slash command
        return jsonify({
            "success": False, 
            "message": "Please use the /scan command in Discord to perform this action."
        })


def has_admin_permission(guild_data):
    """Check if user has admin permission for a guild."""
    try:
        # Convert permissions to int if it's a string
        if 'permissions' in guild_data:
            # Discord API sometimes returns permissions as a string
            permissions = int(guild_data['permissions']) if isinstance(guild_data['permissions'], str) else guild_data['permissions']
            return (guild_data.get('owner', False) or 
                  (permissions & 0x8) == 0x8)  # Check for ADMINISTRATOR permission
        else:
            # If no permissions field, check only owner status
            return guild_data.get('owner', False)
    except (KeyError, ValueError, TypeError) as e:
        # Log the error for debugging
        print(f"Error checking permissions: {e}")
        # If there's any issue with permissions, return False
        return guild_data.get('owner', False)

def check_guild_permission(user_id, guild_id):
    """Check if a user has permission to manage a guild."""
    user_guilds = user_guilds_cache.get(user_id, [])
    guild_id = str(guild_id)  # Ensure guild_id is a string for comparison
    
    for guild in user_guilds:
        if guild['id'] == guild_id and has_admin_permission(guild):
            return True
    
    return False

def encode_params(params):
    """
    URL-encode parameters for OAuth.
    
    Args:
        params: Dictionary of parameters
        
    Returns:
        URL-encoded parameter string
    """
    import urllib.parse
    return '&'.join([f"{key}={urllib.parse.quote(str(params[key]))}" for key in params])