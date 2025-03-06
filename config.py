import os
import json
from dotenv import load_dotenv
from typing import List

# Load environment variables
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# File to store monitored channels
CHANNELS_FILE = 'monitored_channels.json'

# Load channels from file or environment variable
def _load_channels() -> List[str]:
    try:
        if os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, 'r') as f:
                channels = json.load(f)
                return [str(channel) for channel in channels if str(channel).strip()]
    except Exception as e:
        print(f"Error loading channels from file: {e}")

    # Fallback to environment variable if file doesn't exist or has an error
    channels_str = os.getenv('MONITORED_CHANNELS', '')
    return [channel.strip() for channel in channels_str.split(',') if channel.strip()]

# Save channels to file
def _save_channels(channels: List[str]) -> None:
    try:
        with open(CHANNELS_FILE, 'w') as f:
            json.dump(channels, f)
    except Exception as e:
        print(f"Error saving channels to file: {e}")

# Initialize channels from file or environment
MONITORED_CHANNELS = _load_channels()

# Logging Configuration
LOG_LEVEL = 'DEBUG'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Image Configuration
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB maximum file size

# Source Bot Configuration
SOURCE_MESSAGE_ID = 761068064  # Message ID for source detection
SOURCE_WAIT_TIMEOUT = 8  # Seconds to wait for source bot response

# Source URLs configuration
SOURCE_DOMAINS = {
    'e621': ['e621.net'],
    'furaffinity': ['furaffinity.net', 'www.furaffinity.net', 'beta.furaffinity.net'],
    'twitter': ['twitter.com', 'x.com', 'twitter.com/i/web', 'mobile.twitter.com'],
    'bluesky': ['bsky.app', 'bsky.social']
}

# MTProto Configuration
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

def is_monitored_channel(channel_id: str) -> bool:
    """Check if a channel is in the monitored list"""
    return channel_id in MONITORED_CHANNELS

def add_monitored_channel(channel_id: str) -> None:
    """Add a new channel to monitor"""
    if channel_id not in MONITORED_CHANNELS:
        MONITORED_CHANNELS.append(channel_id)
        # Save to file for persistence
        _save_channels(MONITORED_CHANNELS)
        # Also update environment variable as backup
        os.environ['MONITORED_CHANNELS'] = ','.join(MONITORED_CHANNELS)

def get_monitored_channels() -> List[str]:
    """Get list of monitored channel IDs"""
    return MONITORED_CHANNELS

def remove_monitored_channel(channel_id: str) -> None:
    """Remove a channel from monitoring"""
    if channel_id in MONITORED_CHANNELS:
        MONITORED_CHANNELS.remove(channel_id)
        # Save to file for persistence
        _save_channels(MONITORED_CHANNELS)
        # Also update environment variable as backup
        os.environ['MONITORED_CHANNELS'] = ','.join(MONITORED_CHANNELS)