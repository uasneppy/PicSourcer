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
```bash
nano config.py
```
- Enter `API_HASH`, `API_ID`, and `Bot Token`.
- Press `CTRL+X`, then `Y`, then `ENTER` to save.

```bash
nano bot.py
```
- Change your password (`self.BOT_PASSWORD = ""`).
- Press `CTRL+X`, then `Y`, then `ENTER` to save.

### 3️⃣ Start the Bot
```bash
python3 bot.py
```
Everything should run perfectly fine. If any problems arise, search Google for solutions—they should be easily fixable.

---

## 🎮 How to Use the Bot
### 1️⃣ Authenticate Yourself
Use a blank Telegram account, not your main one!

Start `@FindFurryPicBot`. Then:
```plaintext
/password <password>   # Authenticate with the bot's password
/authenticate         # Set up MTProto for source detection
/cancel               # Cancel authentication process if needed
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
- Ensure both authentication steps are completed.
- Verify the bot has the necessary admin permissions.
- Source links appear below captions in monitored channels.

---

## ❓ Need Help?
If you encounter any issues, contact the bot administrator for support.

📌 Stay organized, credit sources, and enhance your Telegram channel with Source Bot!

---

## 📢 Credits
@FindFurryPicBot on Telegram for an amazing pic sourcer. Give it a try on its own and tip the author! I will be donating monthly to support their work. 😊
