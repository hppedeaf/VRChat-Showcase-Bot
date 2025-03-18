"""
Formatting utilities for text and data display.
"""
from datetime import datetime
from typing import Union, Optional
import config


def bytes_to_mb(bytes_value: Union[str, int, float]) -> str:
    """
    Convert bytes to megabytes with formatting.
    
    Args:
        bytes_value: Bytes value as string, int, or float
        
    Returns:
        Formatted string in MB
    """
    if not bytes_value or bytes_value in ("Unknown", "Not specified", "Unavailable"):
        return "Unknown"
    
    try:
        # Convert string to integer if needed
        if isinstance(bytes_value, str) and bytes_value.isdigit():
            bytes_value = int(bytes_value)
            
        # Make sure it's a number
        if not isinstance(bytes_value, (int, float)):
            return "Unknown"
            
        # Convert to MB with 2 decimal places
        mb = float(bytes_value) / (1024 * 1024)
        
        # Format to appropriate size unit
        if mb < 1:
            kb = bytes_value / 1024
            return f"{kb:.1f} KB"
        elif mb > 1000:
            gb = mb / 1024
            return f"{gb:.2f} GB"
        else:
            return f"{mb:.2f} MB"
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