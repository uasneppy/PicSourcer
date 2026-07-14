import os
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==============================================================================
# Directories
# ==============================================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_DIR = DATA_DIR / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# Telegram Bot
# ==============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# ==============================================================================
# Persistent Files
# ==============================================================================

CHANNELS_FILE = DATA_DIR / "monitored_channels.json"

# ==============================================================================
# Logging
# ==============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")

LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ==============================================================================
# Image Processing
# ==============================================================================

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# ==============================================================================
# Source Bot
# ==============================================================================

SOURCE_MESSAGE_ID = 761068064
SOURCE_WAIT_TIMEOUT = 8

SOURCE_DOMAINS = {
    "e621": [
        "e621.net",
    ],
    "furaffinity": [
        "furaffinity.net",
        "www.furaffinity.net",
        "beta.furaffinity.net",
    ],
    "twitter": [
        "twitter.com",
        "x.com",
        "twitter.com/i/web",
        "mobile.twitter.com",
    ],
    "bluesky": [
        "bsky.app",
        "bsky.social",
    ],
}

# ==============================================================================
# Cookie Locations
# ==============================================================================

FURAFFINITY_COOKIES = COOKIES_DIR / "furaffinity_cookies.json"
BLUESKY_COOKIES = COOKIES_DIR / "bluesky_cookies.json"

# ==============================================================================
# Channel Management
# ==============================================================================

def _load_channels() -> List[str]:
    try:
        if CHANNELS_FILE.exists():
            with open(CHANNELS_FILE, "r") as f:
                channels = json.load(f)
                return [
                    str(channel)
                    for channel in channels
                    if str(channel).strip()
                ]
    except Exception as e:
        print(f"Error loading channels: {e}")

    channels_str = os.getenv("MONITORED_CHANNELS", "")

    return [
        channel.strip()
        for channel in channels_str.split(",")
        if channel.strip()
    ]


def _save_channels(channels: List[str]) -> None:
    try:
        with open(CHANNELS_FILE, "w") as f:
            json.dump(channels, f, indent=2)
    except Exception as e:
        print(f"Error saving channels: {e}")


MONITORED_CHANNELS = _load_channels()


def is_monitored_channel(channel_id: str) -> bool:
    return channel_id in MONITORED_CHANNELS


def get_monitored_channels() -> List[str]:
    return MONITORED_CHANNELS


def add_monitored_channel(channel_id: str) -> None:
    if channel_id not in MONITORED_CHANNELS:
        MONITORED_CHANNELS.append(channel_id)
        _save_channels(MONITORED_CHANNELS)


def remove_monitored_channel(channel_id: str) -> None:
    if channel_id in MONITORED_CHANNELS:
        MONITORED_CHANNELS.remove(channel_id)
        _save_channels(MONITORED_CHANNELS)
