# Source Bot

## 🤖 About
Source Bot is an advanced Telegram bot designed to monitor channels, detect images, and automatically find and add source links to posts. With support for multiple platforms, it ensures proper attribution and enhances content management.

## 🚀 Features

### 🔍 Automatic Source Detection
- Scans new posts with images
- Searches across multiple platforms for the original source
- Automatically edits captions to include source links

### 📡 Channel Management
- Add and remove monitored channels
- Pause and resume monitoring as needed

### 🔒 Authentication
- Secure access with password authentication
- Uses MTProto authentication for source detection

### ⚙️ Supported Platforms
- e621
- FurAffinity
- Twitter/X
- Bluesky

### 🛡️ Rate Limiting
- Prevents excessive API usage to ensure stability

## 📖 Getting Started

### Prerequisites
- A Telegram channel where you want to use the bot
- Admin privileges for the bot in the channel
- Edit message permissions enabled
- Channel ID (must start with `-100`)
### - Enter API_HASH and API_ID, along with Bot Token in config.py!
### – Change your password (self.BOT_PASSWORD = "") in bot.py!

### Installation & Setup (Linux/MacOS)

#### 1️⃣ Add the bot to your Telegram channel
Make sure to assign the bot admin rights with message editing permissions.

#### 2️⃣ Get your channel ID
Send a message to `@userinfobot` to retrieve your channel ID. It should start with `-100`.

#### 3️⃣ Authenticate the Bot
Use the following commands in your chat with the bot:

```sh
/password <password>   # Authenticate with the bot's password
/authenticate         # Set up MTProto for source detection
/cancel               # Cancel authentication process if needed
```

#### 4️⃣ Add a Channel for Monitoring
```sh
/add_channel <channel_id>  # Start monitoring a channel
```

#### 5️⃣ Manage Your Channels
```sh
/list_channels         # Show all monitored channels
/delete_channel <id>   # Remove a monitored channel
/stop <id>             # Pause updates for a channel
/resume <id>           # Resume updates for a channel
```

#### 6️⃣ Bot Control Commands
```sh
/start  # Initialize the bot
/pause  # Toggle all updates on/off
/help   # Show available commands
```

## 📊 Channel Status Icons
- 🟢 **Active**: The bot is processing images
- 🔴 **Stopped**: Updates are paused

## 🔧 Troubleshooting & Tips
- Use `/list_channels` to check active channels
- Ensure both authentication steps are completed
- Verify the bot has the necessary admin permissions
- Source links appear below captions in monitored channels

## ❓ Need Help?
If you encounter any issues, contact the bot administrator for support.

---
📌 **Stay organized, credit sources, and enhance your Telegram channel with Source Bot!**

