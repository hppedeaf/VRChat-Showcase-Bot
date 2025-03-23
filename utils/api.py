"""
VRChat API utilities module with improved authentication handling.
Handles interactions with the VRChat API without excessive login attempts.
"""
import re
import os
import time
import json
import logging
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import config as config

# Import VRChatAuthManager for token handling
from utils.vrchat_auth_manager import VRChatAuthManager

# Constants
API_BASE_URL = "https://api.vrchat.cloud/api/1"

class VRChatAPI:
    """Class to handle VRChat API interactions with improved auth handling."""
    
    def __init__(self, auth_token: Optional[str] = None):
        """
        Initialize the VRChat API handler.
        
        Args:
            auth_token: VRChat authentication token (optional, will auto-retrieve if not provided)
        """
        # Set up auth manager
        self.auth_manager = VRChatAuthManager(logger=config.logger)
        
        # Set up auth
        self.auth_token = auth_token or self.auth_manager.get_auth_token()
        self.api_key = None
        self.auth_expiry = None
        self.last_auth_check = 0
        self.user_id = None
        self.username = None
        
        # Create a session for persistent cookies
        self.session = requests.Session()
        
        # Initialize session headers
        self._update_session_headers()
        
        # Get API key once during initialization
        self.api_key = self._get_api_key()
        if self.api_key:
            config.logger.info(f"Successfully initialized VRChat API with key: {self.api_key}")
        else:
            config.logger.warning("Failed to get API key during initialization")
    
    def _update_session_headers(self) -> None:
        """Update session headers with current auth token."""
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://vrchat.com",
            "Referer": "https://vrchat.com/home"
        })
        
        # Set auth cookie if we have a token
        if self.auth_token:
            self.session.cookies.set("auth", self.auth_token, domain="vrchat.com")
            self.session.cookies.set("auth", self.auth_token, domain="api.vrchat.cloud")
    
    def _get_api_key(self) -> Optional[str]:
        """Get the API key from VRChat config."""
        try:
            response = self.session.get(f"{API_BASE_URL}/config")
            if response.status_code != 200:
                config.logger.error(f"Failed to get API config: HTTP {response.status_code}")
                return None
                
            config_data = response.json()
            # Try both old and new field names
            api_key = config_data.get("clientApiKey") or config_data.get("apiKey")
            return api_key
        except Exception as e:
            config.logger.error(f"Failed to get API key: {e}")
            return None
    
    def get_info(self, resource_type: str, resource_id: str, retries: int = config.API_RETRY_ATTEMPTS) -> Optional[Dict[str, Any]]:
        """
        Fetch data from the VRChat API with retry and timeout.
        
        Args:
            resource_type: The type of resource (e.g., "worlds")
            resource_id: The ID of the resource
            retries: Number of retry attempts
        
        Returns:
            JSON response from the VRChat API or None if the request fails
        """
        # Skip requests with "Not specified" as resource_id to avoid 400 errors
        if resource_id == "Not specified":
            config.logger.warning(f"Skipping API request for {resource_type} with 'Not specified' ID")
            return None
            
        url = f"{API_BASE_URL}/{resource_type}/{resource_id}"
        params = {"apiKey": self.api_key} if self.api_key else None
        
        for attempt in range(retries):
            try:
                config.logger.debug(f"Requesting {url} (Attempt {attempt + 1}/{retries})")
                response = self.session.get(url, params=params, timeout=config.API_TIMEOUT)
                
                # Handle different status codes
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    # Auth expired, but don't try to login - just report the error
                    if attempt == 0:
                        config.logger.warning("Auth expired during request. Token may need to be manually updated.")
                    
                    config.logger.error("Authentication failed")
                    return None
                else:
                    config.logger.error(f"API request failed: HTTP {response.status_code}")
                    
                    # Wait before retrying
                    if attempt < retries - 1:
                        time.sleep(config.API_RETRY_DELAY)
                        
            except requests.exceptions.Timeout:
                config.logger.warning(f"Timeout on attempt {attempt + 1}. Retrying...")
                time.sleep(config.API_RETRY_DELAY)
            except requests.exceptions.RequestException as e:
                config.logger.error(f"Request Exception: {e}. Retrying...")
                time.sleep(config.API_RETRY_DELAY)
        
        return None

    def get_world_info(self, world_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a VRChat world.
        
        Args:
            world_id: VRChat world ID
            
        Returns:
            World information dictionary or None if request fails
        """
        world_info = self.get_info("worlds", world_id)
        
        # Log some debug information to help diagnose issues
        if world_info:
            # Safe logging that handles Unicode characters properly
            try:
                # Log limited keys to avoid excessive output
                keys_to_log = list(world_info.keys())[:10]
                config.logger.info(f"World info keys: {', '.join(keys_to_log)}...")
                
                # Safely log name and author
                config.logger.info(f"World name: {world_info.get('name', 'Unknown')}")
                config.logger.info(f"Author: {world_info.get('authorName', 'Unknown')}")
            except UnicodeEncodeError:
                # Fallback if there are encoding issues
                config.logger.info("Retrieved world info (unicode logging error)")
            
            # Check for missing unityPackages data
            if "unityPackages" not in world_info:
                config.logger.warning("World info is missing 'unityPackages' data")
            elif not world_info["unityPackages"]:
                config.logger.warning("World has empty 'unityPackages' array")
                    
        return world_info
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a file in VRChat.
        
        Args:
            file_id: VRChat file ID
            
        Returns:
            File information dictionary or None if request fails
        """
        # Skip invalid file IDs to avoid 400 errors
        if not file_id or file_id == "Not specified":
            config.logger.warning(f"Skipping file info request for invalid file ID: {file_id}")
            return None
            
        return self.get_info("file", file_id)
    
    def get_platform_info(self, world_info: Dict[str, Any]) -> str:
        """
        Determine the platforms a world supports.
        
        Args:
            world_info: World information dictionary from VRChat API
            
        Returns:
            Platform support string (Cross-Platform, PC Only, Quest Only, or Unknown)
        """
        if not world_info:
            config.logger.warning("Cannot determine platform: World info is None")
            return "PC Only"  # Default assumption
                
        # First try using unityPackages data (preferred method)
        unity_packages = world_info.get("unityPackages", [])
        
        if unity_packages:
            # Check for platform info across all packages
            platforms = [package.get("platform", "").lower() for package in unity_packages if package.get("platform")]
            
            config.logger.debug(f"Found platforms: {platforms}")
            
            # Check if any package has a standalonewindows or android platform
            is_standalone = any(p for p in platforms if "standalone" in p)
            is_android = any(p for p in platforms if "android" in p)

            if is_standalone and is_android:
                return "Cross-Platform"
            elif is_standalone:
                return "PC Only"
            elif is_android:
                return "Quest Only"
        else:
            # Log warning but continue with fallback methods
            config.logger.warning("World has empty 'unityPackages' array")
        
        # Fallback method: Try to use other fields to determine platform
        # Check for platform-specific tags
        tags = world_info.get("tags", [])
        if tags:
            config.logger.debug(f"World tags: {tags}")
            
            # Look for platform-specific tags
            quest_tags = ["quest", "android", "mobile"]
            pc_tags = ["pc", "pconly", "windows"]
            
            has_quest_tag = any(tag.lower() for tag in tags if any(q in tag.lower() for q in quest_tags))
            has_pc_tag = any(tag.lower() for tag in tags if any(p in tag.lower() for p in pc_tags))
            
            if has_quest_tag and has_pc_tag:
                return "Cross-Platform"
            elif has_quest_tag:
                return "Quest Only"
            elif has_pc_tag:
                return "PC Only"
        
        # Final fallback: Most worlds are PC by default
        return "PC Only"
        
    def get_world_size(self, file_id: str) -> str:
        """
        Get the size of a world file based on the exact VRChat API response structure.
        
        Args:
            file_id: VRChat file ID
            
        Returns:
            Size in bytes as string or "Unknown" if not available
        """
        # Skip invalid file IDs
        if not file_id or file_id == "Not specified":
            config.logger.warning(f"Cannot determine world size: Invalid file ID ({file_id})")
            return "Unknown"
            
        try:
            # First, try to get file information from /file/{fileId} endpoint
            file_info = self.get_file_info(file_id)
            
            # Debug log the file info to see its structure
            config.logger.debug(f"File info for {file_id}: {json.dumps(file_info, indent=2) if file_info else 'None'}")
            
            # If no file info returned, we can't determine the size
            if not file_info:
                config.logger.warning(f"No file info returned for file_id: {file_id}")
                return "Unknown"
            
            # Strategy 1: Look for size in versions array (preferred method from API docs)
            if "versions" in file_info and isinstance(file_info["versions"], list) and file_info["versions"]:
                # Try each version starting from the most recent (last in array)
                for version in reversed(file_info["versions"]):
                    if not isinstance(version, dict):
                        continue
                        
                    # Check for file object with sizeInBytes
                    if "file" in version and isinstance(version["file"], dict):
                        if "sizeInBytes" in version["file"]:
                            size_bytes = version["file"]["sizeInBytes"]
                            config.logger.info(f"Found world size in versions[].file.sizeInBytes: {size_bytes} bytes")
                            return str(size_bytes)
            
            # Strategy 2: Look for size in any object that might contain size information
            def search_for_size(obj, path=""):
                """Recursively search for size in nested dictionaries"""
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        # Look for size-related keys
                        if isinstance(value, (int, float)) and any(size_key in key.lower() for size_key in ["size", "bytes"]):
                            config.logger.info(f"Found size at {path}.{key}: {value}")
                            return value
                        # Recursively search nested dictionaries
                        elif isinstance(value, (dict, list)):
                            result = search_for_size(value, f"{path}.{key}")
                            if result:
                                return result
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        result = search_for_size(item, f"{path}[{i}]")
                        if result:
                            return result
                return None
            
            # Try to find size information anywhere in the response
            size_value = search_for_size(file_info)
            if size_value:
                return str(size_value)
                
            # If all else fails
            config.logger.warning(f"Could not find size information for file {file_id}")
            return "Unknown"
            
        except Exception as e:
            config.logger.error(f"Error getting world size: {e}")
            return "Unknown"
        
    def get_file_rest_id(self, world_info: Dict[str, Any]) -> str:
        """
        Extract the file ID from world information with debug logging.
        
        Args:
            world_info: World information dictionary from VRChat API
            
        Returns:
            File ID or "Not specified" if not available
        """
        if not world_info:
            config.logger.warning("Cannot extract file ID: World info is None")
            return "Not specified"
        
        # Debug log the world info structure
        config.logger.debug(f"Extracting file ID from world info: {json.dumps(world_info, indent=2)}")
        
        # Method 1: Check unityPackages array first (most reliable)
        if "unityPackages" in world_info and world_info["unityPackages"] and isinstance(world_info["unityPackages"], list):
            # Get the latest unity package (typically the last in the array)
            latest_package = None
            for package in world_info["unityPackages"]:
                # Skip packages without necessary data
                if not isinstance(package, dict) or "assetUrl" not in package:
                    continue
                    
                # Track the latest package
                if latest_package is None or (
                    "created_at" in package and "created_at" in latest_package and 
                    package["created_at"] > latest_package["created_at"]
                ):
                    latest_package = package
            
            # Use the latest package if found
            if latest_package and "assetUrl" in latest_package:
                asset_url = latest_package["assetUrl"]
                config.logger.debug(f"Found assetUrl in latest unityPackage: {asset_url}")
                
                # Extract file ID from URL
                file_id = self._extract_file_id_from_url(asset_url)
                if file_id:
                    config.logger.info(f"Found file ID in unityPackage: {file_id}")
                    return file_id
        
        # Method 2: Try direct assetUrl in world_info
        if "assetUrl" in world_info and world_info["assetUrl"]:
            asset_url = world_info["assetUrl"]
            config.logger.debug(f"Found assetUrl in world_info: {asset_url}")
            
            # Extract file ID from URL
            file_id = self._extract_file_id_from_url(asset_url)
            if file_id:
                config.logger.info(f"Found file ID in assetUrl: {file_id}")
                return file_id
        
        # Method 3: Check assetVersion for a specific fileId
        if "assetVersion" in world_info and isinstance(world_info["assetVersion"], dict):
            if "fileId" in world_info["assetVersion"]:
                file_id = world_info["assetVersion"]["fileId"]
                if file_id:
                    config.logger.info(f"Found file ID in assetVersion: {file_id}")
                    return file_id
        
        # Method 4: Check for file_version.unitypackage.signature
        if "version" in world_info and isinstance(world_info["version"], dict):
            if "file" in world_info["version"] and isinstance(world_info["version"]["file"], dict):
                if "fileId" in world_info["version"]["file"]:
                    file_id = world_info["version"]["file"]["fileId"]
                    config.logger.info(f"Found file ID in version.file: {file_id}")
                    return file_id
        
        # Final fallback: Look for file ID patterns in any field
        for key, value in world_info.items():
            if isinstance(value, str) and value.startswith("file_") and len(value) > 10:
                config.logger.info(f"Found potential file ID in field {key}: {value}")
                return value
        
        config.logger.warning("Could not find file ID in world info")
        return "Not specified"

    def _extract_file_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract file ID from a URL.
        
        Args:
            url: URL to extract file ID from
            
        Returns:
            File ID or None if not found
        """
        if not url:
            return None
            
        # Debug log the URL
        config.logger.debug(f"Extracting file ID from URL: {url}")
            
        # Method 1: Standard URL parsing
        parts = url.split("/")
        for part in parts:
            if part.startswith("file_") and len(part) > 10:
                config.logger.debug(f"Found file ID in URL part: {part}")
                return part
        
        # Method 2: Regex pattern matching
        import re
        match = re.search(r'file_[a-f0-9-]+', url)
        if match:
            config.logger.debug(f"Found file ID via regex: {match.group(0)}")
            return match.group(0)
        
        return None

def extract_world_id(world_link: str) -> Optional[str]:
    """
    Extract the world ID from a VRChat world link.
    Handles both old format (world/ID) and new format (world/ID/info).
    
    Args:
        world_link: VRChat world URL
        
    Returns:
        World ID or None if not found
    """
    # Skip processing if no link provided
    if not world_link:
        return None
        
    # Strip any trailing slashes
    world_link = world_link.rstrip('/')
    
    # Handle the new format with "/info" at the end
    if world_link.endswith('/info'):
        world_link = world_link[:-5]  # Remove "/info" from the end
    
    # Parse the remaining URL
    parts = world_link.split("/")
    if len(parts) >= 5 and parts[-2] == "world":
        return parts[-1]
    
    # Another attempt for different URL formats
    for part in parts:
        # Look for something that matches the world ID format (wrld_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
        if part.startswith("wrld_") and len(part) > 30:
            return part
    
    return None