# Source Bot

## 🤖 About
Source Bot is a Telegram bot that monitors channels, detects images, and automatically finds and adds source links to posts. Reverse-image search is powered by the [Fluffle](https://fluffle.xyz) API, so proper artist attribution is added to your posts with no manual scraping.

## 🚀 Features
### 🔍 Automatic Source Detection
- Scans new posts with images
- Reverse-searches each image with the Fluffle API
- Automatically edits captions to include the source link and artist

### 📡 Channel Management
- Add and remove monitored channels
- Pause and resume monitoring as needed

### 🔒 Authentication
- Secure access with password authentication

### ⚙️ Supported Platforms
Whatever Fluffle indexes, including:
- e621
- Fur Affinity
- Weasyl
- Inkbunny
- Furry Network
- DeviantArt
- Twitter (X)
- Bluesky

### 🛡️ Rate Limiting
- Serialises requests and paces them to respect Fluffle's one-request-at-a-time policy

---

## 📖 Getting Started

### Prerequisites
- A Telegram channel where you want to use the bot
- Admin privileges for the bot in the channel
- Edit message permissions enabled
- Channel ID (must start with `-100`)

---

## 📥 Installation & Setup (Linux/MacOS)
You'll need a dedicated server to run this bot 24/7. You can buy a cloud server or a VPS.

### 1️⃣ Log in to Your Server's Console (Debian or Ubuntu)
```bash
sudo apt update && sudo apt install python3 python3-venv -y
git clone https://github.com/uasneppy/PicSourcer.git
cd PicSourcer
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### 2️⃣ Configure the Bot
The bot is configured with environment variables (a `.env` file in the project
directory is loaded automatically). At minimum set your bot token:

```bash
# .env
TELEGRAM_BOT_TOKEN=123456:your-bot-token-here

# Optional — Fluffle tuning (sensible defaults are built in):
# Identify your app to Fluffle (required by their usage policy):
FLUFFLE_USER_AGENT=PicSourcer/2.0 (by yourname on GitHub)
# Include adult results (default true; needed for most furry art + all Twitter/Bluesky):
FLUFFLE_INCLUDE_NSFW=true
# Confidence tiers that are trusted enough to auto-edit a caption (default exact,tossUp):
FLUFFLE_ACCEPTED_MATCHES=exact,tossUp
# Restrict to specific platforms (comma-separated; empty = all):
# FLUFFLE_PLATFORMS=e621,Fur Affinity,Twitter
```

Set your bot password by editing `self.BOT_PASSWORD` in `bot.py`.

### 3️⃣ Start the Bot
```bash
python3 bot.py
```

You can also run it with Docker — the image no longer needs a headless browser:
```bash
docker build -t picsourcer . && docker run --env-file .env picsourcer
```

---

## 🎮 How to Use the Bot
### 1️⃣ Authenticate Yourself
Start the bot in Telegram, then:
```plaintext
/password <password>   # Authenticate with the bot's password
```

### 2️⃣ Add a Channel for Monitoring
```plaintext
/add_channel <channel_id>  # Start monitoring a channel (bot must be an admin with edit message permissions)
```

### 3️⃣ Manage Your Channels
```plaintext
/list_channels         # Show all monitored channels
/delete_channel <id>   # Remove a monitored channel
/stop <id>             # Pause updates for a channel
/resume <id>           # Resume updates for a channel
```

### 4️⃣ Bot Control Commands
```plaintext
/start  # Initialize the bot
/pause  # Toggle all updates on/off
/help   # Show available commands
```

---

## 📊 Channel Status Icons
- 🟢 **Active**: The bot is processing images
- 🔴 **Stopped**: Updates are paused

---

## 🔧 Troubleshooting & Tips
- Use `/list_channels` to check active channels.
- Verify the bot has the necessary admin permissions.
- Source links appear below captions in monitored channels.
- If most posts get no source, make sure `FLUFFLE_INCLUDE_NSFW=true`.
- Set a descriptive `FLUFFLE_USER_AGENT` so Fluffle can identify your app.

---

## ❓ Need Help?
If you encounter any issues, contact the bot administrator for support.

📌 Stay organized, credit sources, and enhance your Telegram channel with Source Bot!

---

## 📢 Credits
Reverse-image search is powered by [Fluffle](https://fluffle.xyz) — a reverse image search service tailored to the furry community. Please use the API responsibly and set an identifiable `FLUFFLE_USER_AGENT`.
