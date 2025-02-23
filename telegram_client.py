import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import Message, InputFile, InputFileBig
from config import SOURCE_MESSAGE_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH
from logger import logger

class TelegramMTProtoClient:
    def __init__(self):
        if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH]):
            raise ValueError("Missing required Telegram API credentials")

        self.client = TelegramClient('source_bot_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
        self.response_callback = None
        self.waiting_for_response = False
        self.last_sent_message_id = None
        logger.debug("TelegramMTProtoClient initialized")

    async def _safe_disconnect(self):
        """Safely disconnect the client if it's connected"""
        try:
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                logger.debug("Successfully disconnected existing client")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")

    async def start(self):
        """Start the client with retries and proper cleanup"""
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                logger.info(f"Starting MTProto client (attempt {attempt + 1}/{max_retries})")

                # Ensure clean disconnect first
                await self._safe_disconnect()

                # Remove session file if it exists and we're retrying
                if attempt > 0 and os.path.exists('source_bot_session.session'):
                    try:
                        os.remove('source_bot_session.session')
                        logger.info("Removed existing session file for clean start")
                    except Exception as e:
                        logger.error(f"Failed to remove session file: {str(e)}")

                # Connect with the client
                await self.client.connect()

                # Set up event handler for bot responses
                @self.client.on(events.NewMessage(from_users='FindFurryPicBot'))
                async def handle_bot_response(event):
                    try:
                        logger.debug(f"Received message from FindFurryPicBot: {event.message.text}")
                        if not self.waiting_for_response:
                            logger.debug("Not waiting for response, ignoring message")
                            return

                        if not isinstance(event.message, Message):
                            logger.warning("Received non-Message event, ignoring")
                            return

                        if event.message.reply_to_msg_id != self.last_sent_message_id:
                            logger.debug(f"Message {event.message.id} is not a reply to our last message {self.last_sent_message_id}")
                            return

                        logger.info(f"Processing valid response to message {self.last_sent_message_id}")
                        if self.response_callback:
                            logger.debug("Calling response callback")
                            await self.response_callback(event.message.text)
                        self.waiting_for_response = False
                        self.last_sent_message_id = None

                    except Exception as e:
                        logger.error(f"Error handling bot response: {str(e)}", exc_info=True)

                logger.info("MTProto client started successfully")
                return  # Success, exit the retry loop

            except Exception as e:
                logger.error(f"Failed to start MTProto client (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error("Max retries reached, raising last error")
                    raise

    async def authenticate(self, phone_number: str, verification_code: str = None):
        """Handle authentication with provided credentials"""
        try:
            if not await self.client.is_user_authorized():
                if verification_code is None:
                    # Request verification code
                    await self.client.send_code_request(phone_number)
                    logger.info(f"Verification code sent to {phone_number}")
                    return "verification_needed"
                else:
                    # Complete authentication with code
                    await self.client.sign_in(phone_number, verification_code)
                    logger.info("Authentication successful")
                    return "authenticated"
            return "already_authenticated"

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise ValueError(f"Authentication failed: {str(e)}")

    async def is_authenticated(self):
        """Check if client is authenticated"""
        return await self.client.is_user_authorized()

    async def send_image_to_bot(self, image_data: bytes) -> None:
        """Send image to FindFurryPicBot"""
        if not await self.is_authenticated():
            logger.error("MTProto client not authenticated")
            raise ValueError("Authentication required before sending images")

        try:
            # Reset state for new request
            self.waiting_for_response = False
            self.last_sent_message_id = None

            logger.debug("Starting image upload to FindFurryPicBot")
            file = await self.client.upload_file(image_data, file_name='photo.jpg', part_size_kb=512)
            logger.debug("Image uploaded successfully")

            # Send as a photo message with force_reply
            message = await self.client.send_message(
                'FindFurryPicBot',
                file=file,
                reply_to=SOURCE_MESSAGE_ID,
                force_document=False,
                attributes=[]
            )

            logger.debug(f"Sent image to FindFurryPicBot via MTProto, message ID: {message.id}")
            self.last_sent_message_id = message.id
            self.waiting_for_response = True
            logger.debug("Waiting for FindFurryPicBot response")

        except Exception as e:
            logger.error(f"Error sending image via MTProto: {str(e)}", exc_info=True)
            self.waiting_for_response = False
            self.last_sent_message_id = None
            raise

    def set_response_callback(self, callback):
        """Set callback for handling bot responses"""
        self.response_callback = callback

    async def disconnect(self):
        """Disconnect the client"""
        await self._safe_disconnect()
        logger.info("MTProto client disconnected")