import asyncio
from typing import Optional, Dict
from config import SOURCE_WAIT_TIMEOUT, SOURCE_DOMAINS
from logger import logger
from telegram_client import TelegramMTProtoClient

class ImageSearcher:
    def __init__(self):
        self.last_response = None
        self.last_response_time = None
        self.waiting_for_response = False
        self.last_search_time = 0
        self.current_search_id = None
        self.mtproto_client = TelegramMTProtoClient()
        logger.debug("ImageSearcher initialized")

    async def start(self):
        """Start the MTProto client"""
        logger.debug("Starting MTProto client in ImageSearcher")
        await self.mtproto_client.start()
        self.mtproto_client.set_response_callback(self.handle_bot_response)
        logger.info("MTProto client and response callback set up successfully")

    async def search_image(self, bot, image_data: bytes) -> Optional[Dict]:
        """
        Search for image source using MTProto client
        """
        try:
            logger.debug("Starting new image search process")
            # Reset all state for the new search
            self.last_response = None
            self.last_response_time = None
            self.waiting_for_response = False
            self.current_search_id = id(image_data)  # Use unique identifier for this search

            # Basic rate limiting
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_search_time < 2:  # Minimum 2 seconds between searches
                wait_time = 2 - (current_time - self.last_search_time)
                logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)

            # Send image using MTProto client
            logger.info(f"Sending image to FindFurryPicBot via MTProto (search_id: {self.current_search_id})")
            self.waiting_for_response = True
            await self.mtproto_client.send_image_to_bot(image_data)
            self.last_search_time = asyncio.get_event_loop().time()
            search_start_time = self.last_search_time

            # Wait for bot response
            logger.debug(f"Waiting for FindFurryPicBot response (search_id: {self.current_search_id})")
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < SOURCE_WAIT_TIMEOUT:
                if self.last_response and self.last_response_time and self.last_response_time >= search_start_time:
                    source_url = self._extract_source_url(self.last_response)
                    if source_url:
                        source_name = self._get_source_name(source_url)
                        logger.info(f"Found source for search_id {self.current_search_id}: {source_name} - {source_url}")
                        result = {
                            'source_url': source_url,
                            'source_name': source_name
                        }
                        self._reset_state()  # Clear state after successful search
                        return result
                await asyncio.sleep(1)

            logger.warning(f"Timeout waiting for source response (search_id: {self.current_search_id})")
            self._reset_state()
            return None

        except Exception as e:
            logger.error(f"Error during image search: {str(e)}", exc_info=True)
            self._reset_state()
            return None

    def _reset_state(self):
        """Reset all state variables"""
        self.last_response = None
        self.last_response_time = None
        self.waiting_for_response = False
        self.current_search_id = None

    async def handle_bot_response(self, message: str) -> None:
        """Handle response from source detection"""
        if not message or len(message) > 4096:  # Telegram message length limit
            logger.warning(f"Received invalid response: {'too long' if message and len(message) > 4096 else 'empty'}")
            return

        if not self.waiting_for_response or not self.current_search_id:
            logger.warning("Received response when not waiting for one")
            return

        logger.debug(f"Received response from FindFurryPicBot for search_id {self.current_search_id}: {message}")
        self.last_response = message
        self.last_response_time = asyncio.get_event_loop().time()
        self.waiting_for_response = False

    def _extract_source_url(self, message: str) -> Optional[str]:
        """Extract source URL from response"""
        try:
            # Clean and split the message
            lines = [line.strip() for line in message.split('\n') if line.strip()]
            logger.debug(f"Processing {len(lines)} lines from bot response")

            for line in lines:
                # Log the line being processed for debugging
                logger.debug(f"Processing line: {line}")

                # Try to extract markdown-style links first
                import re
                markdown_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
                if markdown_match:
                    url = markdown_match.group(2).strip()
                    # Ensure URL starts with http:// or https://
                    if url.startswith(('http://', 'https://')):
                        if any(domain in url.lower() for platform, domains in SOURCE_DOMAINS.items() for domain in domains):
                            logger.info(f"Found source URL from markdown link: {url}")
                            return url

                # Then try to find regular URLs
                words = line.split()
                for word in words:
                    # Clean up the word and normalize
                    word = word.strip(',.!?()[]{}').replace('\\', '')

                    # Ensure the URL starts with http:// or https://
                    if not word.startswith(('http://', 'https://')):
                        continue

                    # Check if it's a valid source URL
                    if any(domain in word.lower() for platform, domains in SOURCE_DOMAINS.items() for domain in domains):
                        logger.info(f"Found source URL from text: {word}")
                        return word

            logger.debug("No valid source URL found in the message")
            return None

        except Exception as e:
            logger.error(f"Error extracting source URL: {str(e)}", exc_info=True)
            return None

    def _get_source_name(self, url: str) -> str:
        """Get source name from URL"""
        url_lower = url.lower()
        for platform, domains in SOURCE_DOMAINS.items():
            if any(domain in url_lower for domain in domains):
                return platform.capitalize()
        return 'Source'

    async def cleanup(self):
        """Cleanup resources"""
        logger.debug("Cleaning up ImageSearcher resources")
        await self.mtproto_client.disconnect()
        logger.info("ImageSearcher cleanup completed")