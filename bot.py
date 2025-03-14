import signal
import asyncio
import time
import aiohttp
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from config import (
    TELEGRAM_BOT_TOKEN, 
    is_monitored_channel, 
    add_monitored_channel,
    remove_monitored_channel,  
    get_monitored_channels,
    SOURCE_MESSAGE_ID
)
from image_search import ImageSearcher
from utils import download_image
from logger import logger
import sys
import os

# Define conversation states
PHONE_NUMBER, VERIFICATION_CODE = range(2)

class SourceBot:
    def __init__(self):
        self.image_searcher = ImageSearcher()
        self.application = None
        self.start_time = None
        self.is_paused = False
        self.shutdown_event = asyncio.Event()
        self.authenticated_users = set()  
        self.BOT_PASSWORD = "mow"  
        self.stopped_channels = set()
        self.edited_posts = set()  # Track posts that have been edited with source info

        # Set up signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, self._signal_handler)

        logger.info("Bot initialized with enhanced service support")

    def _signal_handler(self, signum, frame):
        """Handle system signals for clean shutdown"""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name} ({signum}), initiating graceful shutdown...")
        self.shutdown_event.set()

    async def cleanup(self):
        """Cleanup resources before shutdown"""
        logger.info("Starting cleanup process...")
        if self.application:
            await self.application.stop()
        await self.image_searcher.cleanup()
        logger.info("Cleanup completed")

    def is_authenticated(self, user_id: int) -> bool:
        """Check if a user is authenticated"""
        return user_id in self.authenticated_users

    async def check_auth(self, update: Update) -> bool:
        """Check authentication and send message if not authenticated"""
        if not self.is_authenticated(update.effective_user.id):
            await update.message.reply_text(
                "You need to authenticate first!\n"
                "Use /password <password> to gain access to bot features."
            )
            return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        await update.message.reply_text(
            "Hello! I'm a bot that finds sources for images posted in channels.\n\n"
            "⚠️ Please authenticate first using:\n"
            "/password <password>\n\n"
            "After authentication, you can:\n"
            "1. Use /authenticate to set up Telegram authentication\n"
            "2. Use /add_channel to start monitoring channels\n"
            "3. Use /delete_channel to remove channels from monitoring\n"
            "4. Use /pause to temporarily stop processing\n"
            "5. Use /list_channels to see monitored channels\n"
            "6. Use /stop <channel_id> to stop updates for a specific channel\n"
            "7. Use /resume <channel_id> to resume updates for a specific channel"
        )

    async def handle_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password authentication"""
        if not context.args:
            await update.message.reply_text("Usage: /password <your_password>")
            return

        provided_password = context.args[0]
        user_id = update.effective_user.id

        if provided_password == self.BOT_PASSWORD:
            self.authenticated_users.add(user_id)
            await update.message.reply_text("Authentication successful! You can now use all bot features.")
            logger.info(f"User {user_id} successfully authenticated")
        else:
            await update.message.reply_text("Invalid password. Please try again.")
            logger.warning(f"Failed password attempt from user {user_id}")

    async def authenticate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start authentication process"""
        if not await self.check_auth(update):
            return ConversationHandler.END

        if await self.image_searcher.mtproto_client.is_authenticated():
            await update.message.reply_text("Already authenticated!")
            return ConversationHandler.END

        keyboard = [[KeyboardButton("❌ Cancel")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(
            "Please enter your phone number (including country code, e.g., +1234567890):",
            reply_markup=reply_markup
        )
        return PHONE_NUMBER

    async def phone_number_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle phone number input"""
        if update.message.text == "❌ Cancel":
            return await self.cancel(update, context)

        phone_number = update.message.text
        context.user_data['phone_number'] = phone_number

        try:
            result = await self.image_searcher.mtproto_client.authenticate(phone_number)
            if result == "verification_needed":
                keyboard = [[KeyboardButton("❌ Cancel")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

                await update.message.reply_text(
                    "I've sent a verification code to your phone. Please enter the code:",
                    reply_markup=reply_markup
                )
                return VERIFICATION_CODE
        except Exception as e:
            await update.message.reply_text(
                f"Authentication failed: {str(e)}\nUse /authenticate to try again.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    async def verification_code_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle verification code input"""
        if update.message.text == "❌ Cancel":
            return await self.cancel(update, context)

        verification_code = update.message.text
        phone_number = context.user_data.get('phone_number')

        try:
            result = await self.image_searcher.mtproto_client.authenticate(phone_number, verification_code)
            if result == "authenticated":
                await update.message.reply_text(
                    "Authentication successful! You can now use the bot's features.",
                    reply_markup=ReplyKeyboardRemove()
                )
            return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(
                f"Authentication failed: {str(e)}\nUse /authenticate to try again.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the conversation"""
        await update.message.reply_text(
            "Authentication cancelled. Use /authenticate to start over.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /add_channel command"""
        if not await self.check_auth(update):
            return

        if not context.args:
            await update.message.reply_text(
                "Please provide the channel ID.\n"
                "Forward a message from your channel to @userinfobot to get the ID."
            )
            return

        channel_id = context.args[0]
        if not channel_id.startswith('-100'):
            await update.message.reply_text(
                "Invalid channel ID format. The ID should start with '-100'."
            )
            return

        try:
            bot_member = await context.bot.get_chat_member(
                chat_id=channel_id,
                user_id=context.bot.id
            )

            if not bot_member.can_edit_messages:
                await update.message.reply_text(
                    "The bot is not an admin in this channel or lacks editing permissions.\n"
                    "Please add the bot as an admin with the following permissions:\n"
                    "- Edit messages\n"
                    "Then try adding the channel again."
                )
                return

            add_monitored_channel(channel_id)
            await update.message.reply_text(
                f"Channel {channel_id} has been added to the monitoring list.\n"
                "The bot will now automatically add source links to new image posts."
            )
            logger.info(f"Added channel {channel_id} to monitoring list")

        except Exception as e:
            if "chat not found" in str(e).lower():
                await update.message.reply_text(
                    "Channel not found. Please make sure:\n"
                    "1. The channel ID is correct\n"
                    "2. The bot is a member of the channel\n"
                    "3. The bot is an admin in the channel"
                )
            else:
                await update.message.reply_text(
                    "Failed to add channel. Please make sure:\n"
                    "1. The bot is a member of the channel\n"
                    "2. The bot is an admin in the channel\n"
                    "3. The channel ID is correct"
                )
            logger.error(f"Error adding channel {channel_id}: {str(e)}")

    async def list_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /list_channels command"""
        if not await self.check_auth(update):
            return
        channels = get_monitored_channels()
        if not channels:
            await update.message.reply_text("No channels are currently being monitored.")
            return

        message = "📋 *Currently monitored channels:*\n\n"
        for channel in channels:
            try:
                chat = await context.bot.get_chat(channel)
                channel_name = chat.title or "Unknown Channel"
                status = "🔴 Stopped" if channel in self.stopped_channels else "🟢 Active"
                channel_name = self.escape_markdown_v2(channel_name)
                message += f"📺 *{channel_name}*\n   ID: `{channel}`\n   Status: {status}\n\n"
            except Exception as e:
                logger.error(f"Failed to get info for channel {channel}: {str(e)}")
                status = "🔴 Stopped" if channel in self.stopped_channels else "🟢 Active"
                message += f"📺 *Unknown Channel*\n   ID: `{channel}`\n   Status: {status}\n\n"

        await update.message.reply_text(message, parse_mode='MarkdownV2')

    async def handle_bot_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle responses from source detection"""
        if not await self.check_auth(update):
            return

        if update.message and update.message.reply_to_message:
            if update.message.reply_to_message.message_id == SOURCE_MESSAGE_ID:
                await self.image_searcher.handle_bot_response(update.message.text)

    async def handle_channel_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new channel posts"""
        try:
            if self.is_paused:
                logger.debug("Skipping post processing - bot is paused")
                return

            # Handle regular, edited, and scheduled posts
            message = None
            is_edited_post = False
            post_type = "unknown"
            if hasattr(update, 'edited_channel_post') and update.edited_channel_post:
                message = update.edited_channel_post
                post_type = "edited"
                is_edited_post = True
            elif hasattr(update, 'channel_post') and update.channel_post:
                message = update.channel_post
                post_type = "regular"

            if not message:
                logger.debug("No message found")
                return

            channel_id = str(message.chat_id)
            if channel_id in self.stopped_channels:
                logger.debug(f"Skipping post processing - channel {channel_id} is stopped")
                return

            # Check if it's a scheduled post and handle accordingly
            is_scheduled = getattr(message, 'forward_date', None) is not None or getattr(message, 'has_scheduled_date', False)
            logger.debug(f"Processing {post_type} channel post (scheduled: {is_scheduled})")

            # We'll use the original message data rather than trying to get_messages
            # The python-telegram-bot library doesn't have get_messages method
            try:
                # Check if we can access this chat
                chat = await context.bot.get_chat(channel_id)
                logger.debug(f"Verified access to channel {channel_id}")
            except Exception as e:
                logger.error(f"Failed to access channel {channel_id}: {str(e)}")
                # Continue with the process even if we can't get fresh chat data

            if self.start_time and message.date and message.date.timestamp() < self.start_time:
                logger.debug(f"Skipping old message from before bot start: {message.message_id}")
                return

            if not is_monitored_channel(channel_id):
                logger.debug(f"Channel {channel_id} is not in monitored list")
                return

            # Get photo from the message
            photo = None
            if message.photo:
                photo = message.photo[-1]
                logger.debug("Found photo in regular message")
            elif hasattr(message, 'photo') and message.photo:
                photo = message.photo[-1]
                logger.debug("Found photo in scheduled message")

            if not photo:
                logger.debug("Post does not contain a photo")
                return
                
            # Create a unique identifier for this post
            post_id = f"{channel_id}:{message.message_id}"
            
            # Check if we've already edited this post
            if post_id in self.edited_posts:
                logger.info(f"Skipping already edited post {message.message_id} in channel {channel_id}")
                return
                
            # If this is an edited post that we didn't edit, skip it (respect manual edits)
            if is_edited_post and post_id not in self.edited_posts:
                logger.info(f"Skipping manually edited post {message.message_id} in channel {channel_id}")
                # Add to edited posts set to prevent future edit attempts
                self.edited_posts.add(post_id)
                return

            original_caption = message.caption or ""

            if len(original_caption) > 1000:  
                logger.warning(f"Caption too long in channel {channel_id}, truncating")
                original_caption = original_caption[:997] + "..."

            logger.info(f"Processing new image post in channel {channel_id}")

            try:
                bot_member = await context.bot.get_chat_member(
                    chat_id=channel_id,
                    user_id=context.bot.id
                )
                logger.debug(f"Bot permissions in channel: {bot_member.status}, can_edit_messages: {bot_member.can_edit_messages}")

                if not bot_member.can_edit_messages:
                    logger.error(f"Bot lacks edit permissions in channel {channel_id}")
                    return

            except Exception as e:
                logger.error(f"Failed to check bot permissions: {str(e)}")
                return

            image_data = await download_image(photo.file_id, context.bot)
            if not image_data:
                logger.error(f"Failed to download image from channel {channel_id}")
                return

            logger.debug(f"Sending image to FindFurryPicBot from channel {channel_id}")
            source = await self.image_searcher.search_image(context.bot, image_data)

            try:
                # Initialize variables to avoid undefined references in error handling
                new_caption = ""
                
                if source:
                    escaped_url = source['source_url']
                    author_nickname = source.get('author_nickname', '')
                    
                    # Create link text with author nickname if available
                    if author_nickname == "BLUESKY_GENERIC_ATTRIBUTION":
                        # Special handling for Bluesky with generic attribution
                        link_text = "*Автор на Bluesky 💎*"
                    elif author_nickname:
                        # Escape any special characters in the nickname for MarkdownV2 format
                        escaped_nickname = self.escape_markdown_v2(author_nickname)
                        link_text = f"*by {escaped_nickname}*"
                    else:
                        link_text = "*by artist*"

                    # Log original caption with any existing links
                    logger.debug(f"Original caption before escaping: {original_caption}")

                    # Properly escape original caption while preserving existing links
                    escaped_caption = self.escape_markdown_v2_preserve_links(original_caption)
                    logger.debug(f"Escaped caption with preserved links: {escaped_caption}")

                    # Build new caption
                    if escaped_caption:
                        new_caption = f"{escaped_caption}\n\n[{link_text}]({escaped_url})"
                    else:
                        new_caption = f"[{link_text}]({escaped_url})"

                    logger.debug(f"Final caption with source attribution: {new_caption}")

                    await context.bot.edit_message_caption(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        caption=new_caption,
                        parse_mode='MarkdownV2'
                    )
                    # Add to edited posts set to prevent re-editing
                    self.edited_posts.add(post_id)
                    logger.info(f"Successfully updated post {message.message_id} in channel {channel_id}")
                else:
                    logger.info(f"No source found for message {message.message_id} in channel {channel_id}, leaving post unedited")

            except Exception as e:
                error_message = str(e).lower()
                if "not enough rights" in error_message:
                    logger.error(f"Bot lacks edit permissions in channel {channel_id}")
                elif "message is not modified" in error_message:
                    logger.info(f"Caption already contains the correct source in channel {channel_id}")
                    # Add to edited posts set to prevent future re-edit attempts
                    self.edited_posts.add(post_id)
                elif "message to edit not found" in error_message:
                    logger.error(f"Message {message.message_id} not found in channel {channel_id}")
                else:
                    logger.error(f"Failed to edit message in channel {channel_id}: {str(e)}")
                    if 'new_caption' in locals():
                        logger.debug(f"Failed caption content: {new_caption}")
                    else:
                        logger.debug("No caption content available")

        except Exception as e:
            logger.error(f"Error handling channel post: {str(e)}", exc_info=True)

    def escape_markdown_v2_preserve_links(self, text: str) -> str:
        """Escape special characters for MarkdownV2 format while preserving links"""
        if not text:
            return ""

        # First, temporarily replace markdown links with placeholders
        links = []
        import re
        pattern = r'\[(.*?)\]\((.*?)\)'

        def replace_link(match):
            links.append(match.group(0))
            return f"LINK_PLACEHOLDER_{len(links)-1}_"

        text_with_placeholders = re.sub(pattern, replace_link, text)

        # Escape special characters
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        escaped_text = text_with_placeholders
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')

        # Restore links
        for i, link in enumerate(links):
            escaped_text = escaped_text.replace(f"LINK_PLACEHOLDER_{i}_", link)

        return escaped_text

    async def pause_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /pause command to toggle bot's processing state"""
        if not await self.check_auth(update):
            return
        self.is_paused = not self.is_paused
        status = "paused" if self.is_paused else "resumed"
        await update.message.reply_text(f"Bot has been {status}. {'No new posts will be processed.' if self.is_paused else 'Now processing new posts.'}")
        logger.info(f"Bot {status} by user command")

    async def stop_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /stop command to disable updates for a specific channel"""
        if not await self.check_auth(update):
            return

        if not context.args:
            await update.message.reply_text(
                "Please provide the channel ID.\n"
                "Usage: /stop <channel_id>"
            )
            return

        channel_id = context.args[0]
        if not channel_id.startswith('-100'):
            await update.message.reply_text(
                "Invalid channel ID format. The ID should start with '-100'."
            )
            return

        if not is_monitored_channel(channel_id):
            await update.message.reply_text(
                "This channel is not in the monitored list.\n"
                "Use /list_channels to see monitored channels."
            )
            return

        self.stopped_channels.add(channel_id)
        await update.message.reply_text(
            f"Updates for channel {channel_id} have been stopped.\n"
            "The bot will no longer modify posts in this channel.\n"
            "Use /resume <channel_id> to resume updates."
        )
        logger.info(f"Updates stopped for channel {channel_id}")

    async def resume_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /resume command to re-enable updates for a specific channel"""
        if not await self.check_auth(update):
            return

        if not context.args:
            await update.message.reply_text(
                "Please provide the channel ID.\n"
                "Usage: /resume <channel_id>"
            )
            return

        channel_id = context.args[0]
        if channel_id not in self.stopped_channels:
            await update.message.reply_text(
                "This channel is not stopped.\n"
                "Use /list_channels to see monitored channels."
            )
            return

        self.stopped_channels.remove(channel_id)
        await update.message.reply_text(
            f"Updates for channel {channel_id} have been resumed.\n"
            "The bot will now process new posts in this channel."
        )
        logger.info(f"Updates resumed for channel {channel_id}")

    async def delete_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /delete_channel command"""
        if not await self.check_auth(update):
            return

        if not context.args:
            await update.message.reply_text(
                "Please provide the channel ID.\n"
                "Usage: /delete_channel <channel_id>"
            )
            return

        channel_id = context.args[0]
        if not channel_id.startswith('-100'):
            await update.message.reply_text(
                "Invalid channel ID format. The ID should start with '-100'."
            )
            return

        if not is_monitored_channel(channel_id):
            await update.message.reply_text(
                "This channel is not in the monitored list.\n"
                "Use /list_channels to see monitored channels."
            )
            return

        remove_monitored_channel(channel_id)
        await update.message.reply_text(
            f"Channel {channel_id} has been removed from the monitoring list.\n"
            "The bot will no longer process posts from this channel."
        )
        logger.info(f"Removed channel {channel_id} from monitoring list")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        if not await self.check_auth(update):
            return

        help_text = """
        🤖 *Source Bot Help*

        *Getting Started*
        1. Add bot to your channel as admin
        2. Get channel ID from @userinfobot (should start with -100)
        3. Complete authentication steps below

        *Authentication Commands*
        • `/password <password>` - Initial bot access authentication
        • `/authenticate` - Set up MTProto for source detection
        • `/cancel` - Cancel authentication process

        *Channel Management*
        • `/add_channel <channel_id>` - Start monitoring channel
        • `/delete_channel <channel_id>` - Remove channel
        • `/list_channels` - Show all monitored channels
        • `/stop <channel_id>` - Pause specific channel
        • `/resume <channel_id>` - Resume specific channel

        *Bot Control*
        • `/start` - Initialize bot
        • `/pause` - Toggle all updates on/off
        • `/help` - Show this help

        *Automatic Features*
        • Image Detection: Monitors new posts with images
        • Source Finding: Searches across multiple platforms
        • Caption Edit: Adds source links automatically
        • Rate Limiting: Prevents API overload

        *Supported Platforms*
        • e621
        • FurAffinity
        • Twitter/X
        • Bluesky

        *Requirements*
        • Bot must be channel admin
        • Edit messages permission required
        • Channel ID must start with -100
        • Initial password authentication
        • MTProto authentication

        *Channel Status Icons*
        • 🟢 Active: Processing images
        • 🔴 Stopped: Updates paused

        *Tips*
        • Use /list_channels to monitor status
        • Check both auth steps are complete
        • Ensure proper admin permissions
        • Source links appear below captions

        Need help? Contact bot administrator.
        """
        await update.message.reply_text(help_text, parse_mode='MarkdownV2')
        logger.debug("Sent help message to user")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the telegram-python-bot library"""
        logger.error(f"Exception while handling an update: {context.error}")


    def escape_markdown_v2(self, text):
        """Escape special characters for MarkdownV2 format"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        return escaped_text

    def run(self):
        """Run the bot with service support"""
        try:
            self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            self.start_time = time.time()
            logger.info(f"Bot starting at timestamp: {self.start_time}")

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('authenticate', self.authenticate)],
                states={
                    PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.phone_number_received)],
                    VERIFICATION_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.verification_code_received)],
                },
                fallbacks=[CommandHandler('cancel', self.cancel)]
            )

            self.application.add_handler(conv_handler)
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("password", self.handle_password))
            self.application.add_handler(CommandHandler("add_channel", self.add_channel))
            self.application.add_handler(CommandHandler("delete_channel", self.delete_channel))  
            self.application.add_handler(CommandHandler("list_channels", self.list_channels))
            self.application.add_handler(CommandHandler("pause", self.pause_bot))
            self.application.add_handler(CommandHandler("stop", self.stop_channel))
            self.application.add_handler(CommandHandler("resume", self.resume_channel))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(MessageHandler(
                (filters.ChatType.CHANNEL & filters.PHOTO) | 
                (filters.ChatType.CHANNEL & filters.UpdateType.EDITED_CHANNEL_POST),
                self.handle_channel_post
            ))
            self.application.add_handler(MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT,
                self.handle_bot_response
            ))

            self.application.add_error_handler(self.error_handler)

            asyncio.get_event_loop().run_until_complete(self.image_searcher.start())
            logger.info("MTProto client initialized")

            pid = os.getpid()
            with open('/tmp/telegram_bot.pid', 'w') as f:
                f.write(str(pid))
            logger.info(f"Bot running with PID: {pid}")

            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                stop_signals=None  
            )

        except Exception as e:
            logger.error(f"Critical error: {str(e)}", exc_info=True)
            sys.exit(1)
        finally:
            asyncio.get_event_loop().run_until_complete(self.cleanup())
            try:
                os.remove('/tmp/telegram_bot.pid')
            except:
                pass
            logger.info("Bot shutdown complete")

if __name__ == "__main__":
    bot = SourceBot()
    bot.run()