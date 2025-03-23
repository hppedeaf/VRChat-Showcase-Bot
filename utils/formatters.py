"""
Formatting utilities for text and data display with improved size handling.
"""
from datetime import datetime
from typing import Union, Optional
import config as config
import re

def bytes_to_mb(bytes_value: Union[str, int, float]) -> str:
    """
    Convert bytes to human-readable size with improved error handling and format detection.
    
    Args:
        bytes_value: Bytes value as string, int, or float
        
    Returns:
        Formatted string with appropriate size unit (KB, MB, GB)
    """
    if not bytes_value or bytes_value in ("Unknown", "Not specified", "Unavailable"):
        return "Unknown"
    
    try:
        # If it's already a formatted string with unit, just return it
        if isinstance(bytes_value, str) and not bytes_value.isdigit():
            # Check if it already has a size unit
            if any(unit in bytes_value for unit in ["KB", "MB", "GB", "TB", "B"]):
                return bytes_value
            
            # Check if it might be a formatted string like "1,234,567"
            if "," in bytes_value:
                # Try to clean it up and convert
                cleaned = bytes_value.replace(",", "")
                if cleaned.isdigit():
                    bytes_value = int(cleaned)
                else:
                    # If it's a JSON string or other non-numeric format, just return
                    return "Unknown"
            elif not bytes_value.isdigit() and not bytes_value.replace('.', '', 1).isdigit():
                # Not a valid number string
                return "Unknown"
        
        # Try different conversion approaches based on type
        if isinstance(bytes_value, str):
            if bytes_value.isdigit():
                bytes_float = float(bytes_value)
            elif bytes_value.replace('.', '', 1).isdigit():  # Check if it's a float string
                bytes_float = float(bytes_value)
            else:
                return "Unknown"
        elif isinstance(bytes_value, (int, float)):
            bytes_float = float(bytes_value)
        else:
            return "Unknown"
        
        # Zero bytes should be shown as "0 B"
        if bytes_float == 0:
            return "0 B"
            
        # Convert to appropriate size unit
        if bytes_float < 1024:
            return f"{bytes_float:.0f} B"
        elif bytes_float < 1024 * 1024:
            kb = bytes_float / 1024
            return f"{kb:.1f} KB"
        elif bytes_float < 1024 * 1024 * 1024:
            mb = bytes_float / (1024 * 1024)
            return f"{mb:.2f} MB"
        else:
            gb = bytes_float / (1024 * 1024 * 1024)
            return f"{gb:.2f} GB"
    except (ValueError, TypeError) as e:
        # Log the error for debugging
        config.logger.error(f"Error converting bytes to MB: {e} (value: {bytes_value}, type: {type(bytes_value)})")
        return "Unknown"
    
def format_vrchat_date(date_str: Optional[str]) -> str:
    """
    Format a VRChat date string to a more readable format.
    
    Args:
        date_str: VRChat date string in format 'YYYY-MM-DDThh:mm:ss.sssZ'
        
    Returns:
        Formatted date string 'YYYY-MM-DD'
    """
    if not date_str:
        return "Unknown"
    
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ')
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        try:
            # Try without milliseconds
            date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return "Unknown"

def truncate_text(text: str, max_length: int = 1024, add_ellipsis: bool = True) -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length of the text
        add_ellipsis: Whether to add "..." to truncated text
        
    Returns:
        Truncated text
    """
    if not text:
        return ""
        
    if len(text) <= max_length:
        return text
    
    if add_ellipsis:
        return text[:max_length-3] + "..."
    else:
        return text[:max_length]

def chunk_text(text: str, max_chunk_size: int = 2000) -> list[str]:
    """
    Split text into chunks of a maximum size.
    
    Args:
        text: Text to split
        max_chunk_size: Maximum size of each chunk
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 > max_chunk_size:
            # If adding this line would exceed the limit, start a new chunk
            chunks.append(current_chunk)
            current_chunk = line
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    # Add the last chunk if there's anything left
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks