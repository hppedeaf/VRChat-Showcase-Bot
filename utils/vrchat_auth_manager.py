"""
Enhanced VRChat authentication management system.
Prioritizes reading auth from saved file without unnecessary login attempts.
"""
import os
import re
import json
import time
import pyotp
import requests
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key

# Constants
AUTH_FILE = "vrchat_auth.json"
AUTH_EXPIRY_DAYS = 14  # VRChat auth tokens typically last for 14-30 days
NOTIFICATION_INTERVAL = 86400  # 24 hours in seconds
API_BASE_URL = "https://api.vrchat.cloud/api/1"

class VRChatAuthManager:
    """Manages VRChat authentication with improved token handling."""
    
    def __init__(self, logger=None, env_file=".env"):
        """
        Initialize the VRChat Auth Manager.
        
        Args:
            logger: Optional logger to use
            env_file: Path to .env file for storing credentials
        """
        self.logger = logger or logging.getLogger("vrchat_auth")
        self.auth_file = Path(AUTH_FILE)
        self.env_file = env_file
        self.auth_data = self._load_auth_data()
        self.session = requests.Session()
        self.api_key = None
        self.last_notification = 0
        self.last_token_check = 0
        self.token_check_interval = 3600  # Check token validity once per hour
        
        # Initialize session with default headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://vrchat.com",
            "Referer": "https://vrchat.com/home"
        })
        
        # Load the API key once
        self._get_api_key()
    
    def _get_api_key(self) -> Optional[str]:
        """
        Get the VRChat API key.
        
        Returns:
            API key or None if not available
        """
        if self.api_key:
            return self.api_key
            
        try:
            self.logger.info("Fetching VRChat API key...")
            response = self.session.get(f"{API_BASE_URL}/config")
            
            if response.status_code == 200:
                config_data = response.json()
                self.api_key = config_data.get("clientApiKey")
                
                if self.api_key:
                    self.logger.info(f"Successfully obtained API key: {self.api_key}")
                    return self.api_key
                else:
                    self.logger.error("API key not found in response")
            else:
                self.logger.error(f"Failed to get API config: HTTP {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Error fetching API key: {e}")
            
        return None
    
    def _load_auth_data(self) -> Dict[str, Any]:
        """
        Load authentication data from file.
        
        Returns:
            Dict with auth data or empty dict if file doesn't exist
        """
        if not self.auth_file.exists():
            return {}
            
        try:
            with open(self.auth_file, 'r') as f:
                data = json.load(f)
                self.logger.info("Loaded authentication data from file")
                return data
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Failed to load auth data: {e}")
            return {}
    
    def _save_auth_data(self, new_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Save authentication data to file.
        
        Args:
            new_data: New data to merge with existing data (optional)
        """
        try:
            # Update existing data with new data if provided
            if new_data:
                self.auth_data.update(new_data)
            
            # Add timestamp
            self.auth_data["updated_at"] = datetime.now().isoformat()
            
            with open(self.auth_file, 'w') as f:
                json.dump(self.auth_data, f, indent=2)
                self.logger.info("Saved authentication data to file")
        except IOError as e:
            self.logger.error(f"Failed to save auth data: {e}")
    
    def get_auth_token(self) -> Optional[str]:
        """
        Get the current auth token, prioritizing saved token over login.
        
        Returns:
            Auth token or None if not available
        """
        # First check environment variable (highest priority)
        env_token = os.getenv("VRCHAT_AUTH")
        if env_token:
            # Update our saved token if different
            if self.auth_data.get("token") != env_token:
                self.auth_data["token"] = env_token
                self.auth_data["source"] = "environment"
                self.auth_data["updated_at"] = datetime.now().isoformat()
                self._save_auth_data()
            return env_token
            
        # Next check saved token
        saved_token = self.auth_data.get("token")
        if saved_token:
            # Only check token validity occasionally to avoid excessive API calls
            current_time = time.time()
            if current_time - self.last_token_check > self.token_check_interval:
                self.last_token_check = current_time
                
                # Check if token is likely expired
                if self._is_token_expired():
                    # Only notify once per notification interval
                    if current_time - self.last_notification > NOTIFICATION_INTERVAL:
                        self.logger.warning(
                            "Authentication token may be expired. Using it anyway, but consider updating VRCHAT_AUTH."
                        )
                        self.last_notification = current_time
                
                # Test token without trying to login if it fails
                is_valid, _ = self.test_token(saved_token)
                if not is_valid:
                    self.logger.warning("Saved token is invalid, but will continue using it to avoid login attempts.")
                    # Don't attempt login, just keep using the token
            
            return saved_token
            
        # No token available
        if time.time() - self.last_notification > NOTIFICATION_INTERVAL:
            self.logger.error(
                "No VRChat authentication token found in file or environment."
            )
            self.last_notification = time.time()
        
        return None
    
    def _is_token_expired(self) -> bool:
        """
        Check if the saved token is likely expired based on timestamp.
        
        Returns:
            True if token is likely expired, False otherwise
        """
        if "updated_at" not in self.auth_data:
            return True
            
        try:
            updated_at = datetime.fromisoformat(self.auth_data["updated_at"])
            expiry_date = updated_at + timedelta(days=AUTH_EXPIRY_DAYS)
            return datetime.now() > expiry_date
        except (ValueError, TypeError):
            return True
    
    def _update_env_file(self, token: str) -> bool:
        """
        Update the .env file with the new token.
        
        Args:
            token: Auth token to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First load existing variables
            load_dotenv(self.env_file)
            
            # Update the VRCHAT_AUTH variable
            set_key(self.env_file, "VRCHAT_AUTH", token)
            
            # Also set in current environment
            os.environ["VRCHAT_AUTH"] = token
            
            self.logger.info(f"Updated VRCHAT_AUTH in {self.env_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update .env file: {e}")
            return False
    
    def _is_token_expired(self) -> bool:
        """
        Check if the saved token is likely expired based on timestamp.
        
        Returns:
            True if token is likely expired, False otherwise
        """
        if "updated_at" not in self.auth_data:
            return True
            
        try:
            updated_at = datetime.fromisoformat(self.auth_data["updated_at"])
            expiry_date = updated_at + timedelta(days=AUTH_EXPIRY_DAYS)
            return datetime.now() > expiry_date
        except (ValueError, TypeError):
            return True
    
    def login(
        self, 
        username: Optional[str] = None, 
        password: Optional[str] = None,
        totp_secret: Optional[str] = None,
        update_env: bool = True
    ) -> Tuple[bool, str]:
        """
        Login to VRChat using credentials and 2FA.
        
        Args:
            username: VRChat username/email (from env if None)
            password: VRChat password (from env if None)
            totp_secret: TOTP secret for 2FA (from env if None)
            update_env: Whether to update the .env file with the new token
            
        Returns:
            Tuple of (success, message)
        """
        # Get credentials from environment if not provided
        username = username or os.getenv("VRCHAT_USERNAME")
        password = password or os.getenv("VRCHAT_PASSWORD")
        totp_secret = totp_secret or os.getenv("VRCHAT_2FA_SECRET")
        
        # Check if we have credentials
        if not username or not password:
            return False, "Missing username or password"
            
        # Make sure we have the API key
        api_key = self._get_api_key()
        if not api_key:
            return False, "Failed to get VRChat API key"
            
        self.logger.info(f"Attempting to login as: {username}")
        
        try:
            # Step 1: Initial authentication with username/password
            auth = (username, password)
            params = {"apiKey": api_key}
            
            response = self.session.get(
                f"{API_BASE_URL}/auth/user",
                params=params,
                auth=auth
            )
            
            if response.status_code != 200:
                return False, f"Authentication failed: HTTP {response.status_code}"
                
            auth_data = response.json()
            
            # Step 2: Handle 2FA if required
            if auth_data.get("requiresTwoFactorAuth"):
                self.logger.info("2FA required, generating TOTP code...")
                
                # Make sure we have a TOTP secret
                if not totp_secret:
                    return False, "2FA is required but no TOTP secret provided"
                    
                # Generate TOTP code
                try:
                    totp = pyotp.TOTP(totp_secret)
                    totp_code = totp.now()
                    self.logger.info(f"Generated 2FA code: {totp_code}")
                except Exception as e:
                    return False, f"Failed to generate 2FA code: {e}"
                
                # Submit 2FA verification
                response = self.session.post(
                    f"{API_BASE_URL}/auth/twofactorauth/totp/verify",
                    params=params,
                    json={"code": totp_code}
                )
                
                if response.status_code != 200:
                    return False, f"2FA verification failed: HTTP {response.status_code}"
                    
                verify_response = response.json()
                if not verify_response.get("verified", False):
                    return False, "2FA verification failed: Not verified"
                    
                self.logger.info("2FA verification successful")
                
                # Confirm login after 2FA
                response = self.session.get(f"{API_BASE_URL}/auth/user", params=params)
                
                if response.status_code != 200:
                    return False, f"Login confirmation failed: HTTP {response.status_code}"
                    
                auth_data = response.json()
            
            # Extract auth token from cookies
            auth_token = self._extract_auth_token_from_cookies()
            if not auth_token:
                return False, "Failed to extract auth token from cookies"
                
            # Get user information
            user_id = auth_data.get("id")
            display_name = auth_data.get("displayName")
            
            if not user_id:
                return False, "Failed to get user ID from response"
                
            # Save auth data
            new_auth_data = {
                "token": auth_token,
                "user_id": user_id,
                "username": display_name,
                "source": "login"
            }
            self._save_auth_data(new_auth_data)
            
            # Update .env file if requested
            if update_env:
                self._update_env_file(auth_token)
            
            return True, f"Successfully logged in as {display_name} (ID: {user_id})"
            
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False, f"Login failed: {str(e)}"
    
    def test_token(self, token: Optional[str] = None) -> Tuple[bool, str]:
        """
        Test if the auth token is valid by making a request to VRChat API.
        
        Args:
            token: Auth token to test, or None to use current token
            
        Returns:
            Tuple of (is_valid, message)
        """
        token = token or self.get_auth_token()
        
        if not token:
            return False, "No authentication token available"
            
        try:
            # Update session cookie with the token
            self.session.cookies.set("auth", token, domain="api.vrchat.cloud")
            
            # Try to get current user info
            response = self.session.get(f"{API_BASE_URL}/auth/user")
            
            if response.status_code == 200:
                user_data = response.json()
                user_id = user_data.get("id")
                username = user_data.get("displayName")
                
                if user_id:
                    # Update auth data with user info
                    self.auth_data.update({
                        "token": token,
                        "user_id": user_id,
                        "username": username,
                        "updated_at": datetime.now().isoformat(),
                        "expires_at": (datetime.now() + timedelta(days=AUTH_EXPIRY_DAYS)).isoformat()
                    })
                    self._save_auth_data()
                    
                    return True, f"Authentication successful as {username} (ID: {user_id})"
                else:
                    return False, "Authentication successful but unable to get user data"
            elif response.status_code == 401:
                return False, "Authentication token is invalid or expired"
            else:
                return False, f"Unexpected response: HTTP {response.status_code}"
                
        except requests.RequestException as e:
            return False, f"Request error: {e}"
    
    def update_token(self, new_token: str, update_env: bool = True) -> Tuple[bool, str]:
        """
        Update the authentication token.
        
        Args:
            new_token: New auth token
            update_env: Whether to update the .env file
            
        Returns:
            Tuple of (success, message)
        """
        # Test the new token first
        is_valid, message = self.test_token(new_token)
        
        if is_valid:
            # Save the new token
            self.auth_data["token"] = new_token
            self.auth_data["source"] = "manual"
            self.auth_data["updated_at"] = datetime.now().isoformat()
            self._save_auth_data()
            
            # Update environment variable if possible
            try:
                # This only works within the current process
                os.environ["VRCHAT_AUTH"] = new_token
            except Exception:
                pass
                
            # Update .env file if requested
            if update_env:
                self._update_env_file(new_token)
                
            return True, f"Authentication token updated: {message}"
        else:
            return False, f"Failed to update token: {message}"
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get authentication status information.
        
        Returns:
            Dict with status details
        """
        token = self.get_auth_token()
        
        if not token:
            return {
                "valid": False,
                "message": "No authentication token available",
                "expires_in": None,
                "user": None
            }
            
        # Check validity
        if "updated_at" in self.auth_data:
            try:
                updated_at = datetime.fromisoformat(self.auth_data["updated_at"])
                expiry_date = updated_at + timedelta(days=AUTH_EXPIRY_DAYS)
                days_left = (expiry_date - datetime.now()).days
                
                return {
                    "valid": days_left > 0,
                    "message": f"Token expires in approximately {days_left} days",
                    "expires_in": days_left,
                    "user": self.auth_data.get("username"),
                    "user_id": self.auth_data.get("user_id"),
                    "source": self.auth_data.get("source", "unknown")
                }
            except (ValueError, TypeError):
                pass
                
        # If we can't determine from saved data, test the token
        is_valid, message = self.test_token(token)
        
        return {
            "valid": is_valid,
            "message": message,
            "expires_in": AUTH_EXPIRY_DAYS if is_valid else 0,
            "user": self.auth_data.get("username"),
            "user_id": self.auth_data.get("user_id"),
            "source": self.auth_data.get("source", "unknown")
        }


# Command-line functionality
if __name__ == "__main__":
    import argparse
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("vrchat_auth")
    
    # Create argument parser
    parser = argparse.ArgumentParser(description="VRChat Authentication Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check authentication status")
    
    # Login command
    login_parser = subparsers.add_parser("login", help="Login with credentials")
    login_parser.add_argument("--username", help="VRChat username/email")
    login_parser.add_argument("--password", help="VRChat password")
    login_parser.add_argument("--totp-secret", help="TOTP secret for 2FA")
    login_parser.add_argument("--no-env-update", action="store_true", help="Don't update .env file")
    
    # Update token command
    update_parser = subparsers.add_parser("update", help="Update auth token")
    update_parser.add_argument("--token", required=True, help="New auth token")
    update_parser.add_argument("--no-env-update", action="store_true", help="Don't update .env file")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create auth manager
    auth_manager = VRChatAuthManager(logger=logger)
    
    # Handle commands
    if args.command == "status":
        status = auth_manager.get_status()
        print(f"Authentication Status: {'Valid' if status['valid'] else 'Invalid'}")
        print(f"Message: {status['message']}")
        if status['user']:
            print(f"User: {status['user']}")
        if status['expires_in'] is not None:
            print(f"Expires in: {status['expires_in']} days")
        print(f"Source: {status['source']}")
    
    elif args.command == "login":
        success, message = auth_manager.login(
            username=args.username,
            password=args.password,
            totp_secret=args.totp_secret,
            update_env=not args.no_env_update
        )
        
        if success:
            print(f"Login successful: {message}")
            print("Authentication token has been saved.")
            if not args.no_env_update:
                print("The .env file has been updated with the new token.")
        else:
            print(f"Login failed: {message}")
            print("Please check your credentials and try again.")
    
    elif args.command == "update":
        success, message = auth_manager.update_token(
            args.token,
            update_env=not args.no_env_update
        )
        
        if success:
            print(f"Token update successful: {message}")
            if not args.no_env_update:
                print("The .env file has been updated with the new token.")
        else:
            print(f"Token update failed: {message}")
            print("Please check the token and try again.")
    
    else:
        # No command or invalid command
        parser.print_help()