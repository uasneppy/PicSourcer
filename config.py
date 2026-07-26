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

LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# Telegram Bot
# ==============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

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

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB (Telegram download cap)

# ==============================================================================
# Fluffle Reverse-Image Search  (https://api.fluffle.xyz/v1/search)
# ==============================================================================
# Fluffle replaces both the old @FindFurryPicBot MTProto search and the per-site
# scraping: a single request returns the source URL, platform and artist credits.

# Fluffle requires every client to identify itself with a descriptive User-Agent
# of the form "applicationName/applicationVersion (by yourName on somePlatform)".
FLUFFLE_API_URL = os.getenv("FLUFFLE_API_URL", "https://api.fluffle.xyz/v1/search")
FLUFFLE_USER_AGENT = os.getenv(
    "FLUFFLE_USER_AGENT",
    "PicSourcer/2.0 (by uasneppy on GitHub)",
)

# Furry art is predominantly adult, so include NSFW results by default — otherwise
# most posts return no match. Fluffle also treats every Twitter/Bluesky result as
# explicit, so those need this enabled too.
FLUFFLE_INCLUDE_NSFW = os.getenv("FLUFFLE_INCLUDE_NSFW", "true").lower() == "true"

# Number of candidate matches Fluffle should return (Fluffle accepts 8–32).
FLUFFLE_LIMIT = max(8, min(32, int(os.getenv("FLUFFLE_LIMIT", "32"))))

# Restrict the search to specific platforms (comma-separated). Empty = search all.
# Valid names: "Fur Affinity", "Twitter", "e621", "Weasyl", "Furry Network",
#              "DeviantArt", "Inkbunny", "Bluesky"
FLUFFLE_PLATFORMS = [
    p.strip() for p in os.getenv("FLUFFLE_PLATFORMS", "").split(",") if p.strip()
]

# Network timeout (seconds) for a single Fluffle request.
FLUFFLE_TIMEOUT = int(os.getenv("FLUFFLE_TIMEOUT", "30"))

# Longest edge (px) an image is resized to before uploading to Fluffle. Keeps the
# payload comfortably under Fluffle's 4 MiB / 16 MP limits and speeds up matching.
FLUFFLE_MAX_DIMENSION = int(os.getenv("FLUFFLE_MAX_DIMENSION", "2048"))

# ------------------------------------------------------------------------------
# Result selection
# ------------------------------------------------------------------------------

# Fluffle grades each result by confidence. The list also defines preference
# (best first). Only tiers listed in ACCEPTED_MATCHES are trusted enough to
# auto-edit a channel caption. Compared case-insensitively (Fluffle returns
# e.g. "exact"/"tossUp"/"alternative"/"unlikely"), so keep these lowercase.
MATCH_ORDER = ["exact", "tossup", "alternative", "unlikely"]

ACCEPTED_MATCHES = {
    m.strip().lower()
    for m in os.getenv("FLUFFLE_ACCEPTED_MATCHES", "exact,tossUp").split(",")
    if m.strip()
}

# When several trusted results tie on confidence, prefer the platform with the
# richest / most reliable artist attribution. Lower number = higher priority.
# NOTE: Fluffle's response `platform` field uses camelCase machine names
# ("furAffinity", "deviantArt", ...). Keys here are normalised to
# lowercase-alphanumeric so casing/spacing never matters when looking them up.
PLATFORM_PRIORITY = {
    "e621": 0,
    "furaffinity": 1,
    "weasyl": 2,
    "inkbunny": 3,
    "furrynetwork": 4,
    "deviantart": 5,
    "twitter": 6,
    "bluesky": 7,
}

# Pretty, human-readable names for captions, keyed by the same normalised name.
PLATFORM_DISPLAY_NAMES = {
    "e621": "e621",
    "furaffinity": "Fur Affinity",
    "weasyl": "Weasyl",
    "inkbunny": "Inkbunny",
    "furrynetwork": "Furry Network",
    "deviantart": "DeviantArt",
    "twitter": "Twitter",
    "bluesky": "Bluesky",
}

# e621 artist "tags" that are not real artist names — filtered out of credits.
META_ARTIST_TAGS = {
    "unknown_artist", "anonymous_artist", "avoid_posting", "third-party_edit",
    "sound_warning", "epilepsy_warning", "ai_generated", "stable_diffusion",
    "novelai",
}

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
