import asyncio
import cloudscraper
import aiohttp
import os
from typing import Optional, Dict
from urllib.parse import urlparse
from config import SOURCE_WAIT_TIMEOUT, SOURCE_DOMAINS
from logger import logger
from telegram_client import TelegramMTProtoClient
from bs4 import BeautifulSoup
import re
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Create a cloudscraper instance with anti-bot bypass capabilities
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

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
                        author_nickname = await self.extract_author_nickname(source_url)
                        logger.info(f"Found source for search_id {self.current_search_id}: {source_name} - {source_url}")
                        if author_nickname:
                            logger.info(f"Extracted author nickname: {author_nickname}")
                        
                        result = {
                            'source_url': source_url,
                            'source_name': source_name,
                            'author_nickname': author_nickname
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
            
            # Storage for found URLs by platform
            found_urls = {
                'e621': '',
                'furaffinity': '',
                'twitter': '',
                'bluesky': ''
            }

            for line in lines:
                # Log the line being processed for debugging
                logger.debug(f"Processing line: {line}")

                # Try to extract markdown-style links first
                markdown_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
                if markdown_match:
                    url = markdown_match.group(2).strip()
                    # Ensure URL starts with http:// or https://
                    if url.startswith(('http://', 'https://')):
                        # Check which platform the URL belongs to
                        for platform, domains in SOURCE_DOMAINS.items():
                            if any(domain in url.lower() for domain in domains):
                                logger.info(f"Found {platform} URL from markdown link: {url}")
                                found_urls[platform] = url
                                break

                # Then try to find regular URLs
                words = line.split()
                for word in words:
                    # Clean up the word and normalize
                    word = word.strip(',.!?()[]{}').replace('\\', '')

                    # Ensure the URL starts with http:// or https://
                    if not word.startswith(('http://', 'https://')):
                        continue

                    # Check which platform the URL belongs to
                    for platform, domains in SOURCE_DOMAINS.items():
                        if any(domain in word.lower() for domain in domains):
                            logger.info(f"Found {platform} URL from text: {word}")
                            found_urls[platform] = word
                            break
            
            # Prioritize e621 if available
            if found_urls['e621']:
                logger.info(f"Prioritizing e621 URL: {found_urls['e621']}")
                return found_urls['e621']
            
            # Fallback to other platforms in this order: FurAffinity, Twitter, Bluesky
            for platform in ['furaffinity', 'twitter', 'bluesky']:
                if found_urls[platform]:
                    logger.info(f"Using {platform} URL: {found_urls[platform]}")
                    return found_urls[platform]

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
        
    async def extract_author_nickname(self, url: str) -> str:
        """
        Extract author nickname from source URL
        Returns empty string if nickname can't be extracted
        For Bluesky, returns a special marker for generic attribution
        """
        # Check if this is a Bluesky URL - if so, return special marker for generic attribution
        if 'bsky.app' in url.lower():
            logger.info("Detected Bluesky URL - using generic attribution")
            return "BLUESKY_GENERIC_ATTRIBUTION"
            
        try:
            url_lower = url.lower()
            
            # Define domain handlers for different sites
            # This makes the code more maintainable and organized
            domain_handlers = {
                'e621.net': self._extract_e621_username,
                'furaffinity.net': self._extract_furaffinity_username,
                'twitter.com': self._extract_twitter_username,
                'x.com': self._extract_twitter_username
                # Removed Bluesky handler as per request - will use generic attribution
            }
            
            # First check if we have a dedicated handler for this domain
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '')
            
            for domain_pattern, handler in domain_handlers.items():
                if domain_pattern in domain:
                    logger.debug(f"Using dedicated handler for {domain_pattern}")
                    return await handler(url)
            
            # Generic fallback for unknown domains
            logger.debug(f"No specific handler for domain: {domain}, using generic extraction")
            
            # For unsupported domains, try to extract from URL structure
            if '/user/' in url_lower:
                # Common pattern for many sites
                username_match = re.search(r'/user/([a-zA-Z0-9_-]+)', url_lower)
                if username_match:
                    return username_match.group(1)
            
            # Return empty string if extraction fails
            logger.warning(f"No extraction method for {domain}")
            return ""
        except Exception as e:
            logger.error(f"Error extracting author nickname: {str(e)}", exc_info=True)
            return ""
    
    async def _extract_e621_username(self, url: str) -> str:
        """Extract username from e621 URL using API"""
        url_lower = url.lower()
        # Extract post ID from URL
        post_id_match = re.search(r'e621\.net/posts/(\d+)', url_lower)
        if post_id_match:
            post_id = post_id_match.group(1)
            
            # Make an async API request to get the artist information
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {'User-Agent': 'SourceBot/1.0'}
                    async with session.get(f"https://e621.net/posts/{post_id}.json", headers=headers) as response:
                        if response.status == 200:
                            post_data = await response.json()
                            # Extract artist tags
                            if 'post' in post_data and 'tags' in post_data['post'] and 'artist' in post_data['post']['tags']:
                                artists = post_data['post']['tags']['artist']
                                if artists:
                                    # Clean up artist names and join multiple artists with comma
                                    cleaned_artists = []
                                    for artist in artists:
                                        # Remove common suffixes and tags like:
                                        # - artist name_(artist)
                                        # - conditional_dnp / conditional_use
                                        artist = re.sub(r'_\(artist\)$', '', artist)
                                        artist = re.sub(r'^conditional_[a-z_]+$', '', artist)
                                        if artist.strip():  # Only add non-empty strings
                                            cleaned_artists.append(artist)
                                    
                                    if cleaned_artists:
                                        return ', '.join(cleaned_artists)
                                    
                        logger.debug(f"Failed to get artist info for e621 post {post_id}")
            except Exception as e:
                logger.error(f"Error fetching e621 post data: {str(e)}")
        
        return ""
            
    async def _extract_furaffinity_username(self, url: str) -> str:
        """
        Extract username from FurAffinity URL using multiple methods
        This function tries Selenium first, then falls back to cloudscraper if needed
        """
        url_lower = url.lower()
        
        # Check if it's a user page - direct extraction is possible
        user_match = re.search(r'furaffinity\.net/user/([a-zA-Z0-9_-]+)', url_lower)
        if user_match:
            username = user_match.group(1)
            logger.info(f"Extracted FurAffinity username directly from URL: {username}")
            return username
        
        # Check if it's a view page
        view_match = re.search(r'furaffinity\.net/view/(\d+)', url_lower)
        if not view_match:
            logger.warning(f"URL {url} doesn't match FurAffinity view pattern")
            return ""
            
        # First try with Selenium which provides the best JavaScript-rendered content access
        logger.debug(f"Attempting to extract FurAffinity username using Selenium from {url}")
        
        # Try Selenium approach first
        try:
            username = await self._extract_furaffinity_username_with_selenium(url)
            if username:
                logger.info(f"Successfully extracted FurAffinity username with Selenium: {username}")
                return username
        except Exception as selenium_error:
            logger.error(f"Selenium extraction failed: {str(selenium_error)}")
            
        # Fallback to cloudscraper if Selenium fails
        logger.debug(f"Selenium extraction failed, trying cloudscraper for {url}")
        
        # Create a cloudscraper instance if we don't already have one
        if not hasattr(self, 'scraper') or self.scraper is None:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                },
                debug=False
            )
        
        # For FurAffinity view pages, we need to scrape the page to get the artist
        try:
            logger.debug(f"Fetching FurAffinity page from {url} using cloudscraper")
            
            # Check for cookie files in multiple locations
            cookie_paths = [
                os.path.join(os.path.dirname(__file__), 'furaffinity_cookies.json'),  # Same directory
                os.path.join(os.path.dirname(__file__), 'cookies', 'furaffinity_cookies.json'),  # Cookies subdirectory
                'furaffinity_cookies.json',  # Root directory
                os.path.join('cookies', 'furaffinity_cookies.json')  # Cookies subdirectory from root
            ]
            
            cookies_dict = {}
            cookie_file = None
            
            # Find and load cookies if available
            for path in cookie_paths:
                if os.path.exists(path):
                    cookie_file = path
                    logger.debug(f"Found FurAffinity cookies at: {path}")
                    break
            
            if cookie_file:
                try:
                    with open(cookie_file, 'r') as f:
                        cookies_json = json.load(f)
                    
                    if cookies_json and len(cookies_json) > 0:
                        logger.debug(f"Loading {len(cookies_json)} FurAffinity cookies from {cookie_file}")
                        
                        # Check for required authentication cookies
                        auth_cookies = [c for c in cookies_json if c.get('name') in ['a', 'b']]
                        if auth_cookies:
                            logger.debug(f"Found {len(auth_cookies)} authentication cookies")
                        else:
                            logger.warning("No critical authentication cookies (a, b) found")
                        
                        # Convert to dictionary format for requests
                        for cookie in cookies_json:
                            name = cookie.get('name')
                            value = cookie.get('value')
                            if name and value:
                                cookies_dict[name] = value
                        
                        logger.debug(f"Converted {len(cookies_dict)} cookies to dictionary format")
                    else:
                        logger.debug("Cookie file exists but is empty")
                except Exception as e:
                    logger.error(f"Error loading cookies: {str(e)}")
            else:
                logger.debug("No FurAffinity cookies file found. Create one using furaffinity_cookie_tool.py")
            
            # Use cloudscraper to bypass anti-bot protections
            # Add User-Agent to appear more like a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.furaffinity.net/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            loop = asyncio.get_event_loop()
            scraper = self.scraper if hasattr(self, 'scraper') else cloudscraper.create_scraper() 
            response = await loop.run_in_executor(
                None, 
                lambda: scraper.get(
                    url, 
                    cookies=cookies_dict if cookies_dict else None,
                    headers=headers,
                    timeout=15
                )
            )
            
            if response.status_code == 200:
                html = response.text
                logger.debug("Successfully fetched FurAffinity page HTML")
                
                # Check if we've hit a login wall
                login_indicators = ["Log in to FurAffinity", "login form", "password", "Please log in"]
                if any(indicator in html for indicator in login_indicators) and cookies_dict:
                    logger.warning("Hit FurAffinity login wall despite cookies - possibly expired cookies")
                
                # Parse the HTML with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Method 1: Look for submission username in submission-id-sub-container
                username_container = soup.select_one('a.iconusername')
                if username_container:
                    username = username_container.get_text().strip()
                    logger.info(f"Extracted FurAffinity artist name from iconusername: {username}")
                    return username
                
                # Method 2: Try author link with specific class
                author_link = soup.select_one('a.author')
                if author_link:
                    username = author_link.get_text().strip()
                    logger.info(f"Extracted FurAffinity artist name from author link: {username}")
                    return username
                
                # Method 3: Look for submission author container
                submission_author = soup.select_one('#submission-author')
                if submission_author:
                    author_link = submission_author.select_one('a')
                    if author_link:
                        username = author_link.get_text().strip()
                        logger.info(f"Extracted FurAffinity artist name from submission author: {username}")
                        return username
                
                # Method 4: Parse from href pattern
                user_link = soup.select_one('a[href^="/user/"]')
                if user_link:
                    href = user_link.get('href', '')
                    username_match = re.search(r'/user/([a-zA-Z0-9_-]+)', href)
                    if username_match:
                        username = username_match.group(1)
                        logger.info(f"Extracted FurAffinity username from URL: {username}")
                        return username
            else:
                logger.warning(f"Failed to fetch FurAffinity page. Status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching FurAffinity HTML: {str(e)}", exc_info=True)
        
        # Try with fallback regex extraction from URL if HTML scraping failed
        try:
            # Sometimes the URL might include the username in another format
            username_fallback = re.search(r'by[=/]([a-zA-Z0-9_-]+)', url)
            if username_fallback:
                username = username_fallback.group(1)
                logger.info(f"Extracted FurAffinity username from URL fallback: {username}")
                return username
        except Exception as e:
            logger.error(f"Error in regex fallback extraction: {str(e)}")
        
        # No username could be extracted
        return ""
        
    async def _extract_twitter_username(self, url: str) -> str:
        """
        Extract username from Twitter/X URL using multiple methods
        This function tries Selenium first, then falls back to cloudscraper if needed
        """
        url_lower = url.lower()
        
        # First, try to extract username from URL
        twitter_match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)(?:/status/|$)', url_lower)
        username_from_url = twitter_match.group(1) if twitter_match else ""
        
        # If we got a valid username from the URL and it's not "user" (placeholder), return it directly
        if username_from_url and username_from_url != "user" and username_from_url not in ["i", "search", "home", "explore", "notifications", "messages"]:
            logger.info(f"Successfully extracted Twitter username from URL: {username_from_url}")
            return username_from_url
            
        # For tweets with "user" format URLs or tweets where the URL doesn't contain the username directly,
        # we need more advanced extraction
        # First, clean and normalize the URL
        # 1. Convert x.com/user URLs to x.com/i format
        twitter_url = url.replace("/user/", "/i/")
        
        # 2. If it's a standard tweet URL, normalize to i/status instead of just status
        if '/status/' in twitter_url and '/i/status/' not in twitter_url:
            twitter_url = twitter_url.replace('/status/', '/i/status/')
            
        # 3. Handle mobile twitter URLs
        if 'mobile.twitter.com' in twitter_url:
            twitter_url = twitter_url.replace('mobile.twitter.com', 'twitter.com')
            
        # 4. Make sure to use https
        if twitter_url.startswith('http://'):
            twitter_url = 'https://' + twitter_url[7:]
            
        logger.debug(f"Normalized Twitter URL: {twitter_url}")
        
        # Try Selenium approach first
        try:
            logger.debug(f"Attempting to extract Twitter username using Selenium from {twitter_url}")
            username = await self._extract_twitter_username_with_selenium(twitter_url)
            if username:
                logger.info(f"Successfully extracted Twitter username with Selenium: {username}")
                return username
        except Exception as selenium_error:
            logger.error(f"Selenium extraction for Twitter failed: {str(selenium_error)}")
            
        # Fallback to cloudscraper if Selenium fails
        logger.debug(f"Selenium extraction failed, trying cloudscraper for {twitter_url}")
        
        # Create a cloudscraper instance if we don't already have one
        if not hasattr(self, 'scraper') or self.scraper is None:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                },
                debug=False
            )
        
        try:
            # Set up headers to look more like a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://twitter.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Try to find cookie files in multiple locations
            cookie_paths = [
                os.path.join(os.path.dirname(__file__), 'twitter_cookies.json'),  # Same directory
                os.path.join(os.path.dirname(__file__), 'cookies', 'twitter_cookies.json'),  # Cookies subdirectory
                'twitter_cookies.json',  # Root directory
                os.path.join('cookies', 'twitter_cookies.json')  # Cookies subdirectory from root
            ]
            
            cookies_dict = {}
            cookie_file = None
            
            # Find and load cookies if available
            for path in cookie_paths:
                if os.path.exists(path):
                    cookie_file = path
                    logger.debug(f"Found Twitter cookies at: {path}")
                    break
            
            if cookie_file:
                try:
                    with open(cookie_file, 'r') as f:
                        cookies_json = json.load(f)
                    
                    if cookies_json and len(cookies_json) > 0:
                        logger.debug(f"Loading {len(cookies_json)} Twitter cookies from {cookie_file}")
                        
                        # Check for required authentication cookies
                        auth_cookies = [c for c in cookies_json if c.get('name') in ['auth_token', 'ct0', 'twid']]
                        if auth_cookies:
                            logger.debug(f"Found {len(auth_cookies)} authentication cookies")
                        else:
                            logger.warning("No critical authentication cookies (auth_token, ct0, twid) found")
                        
                        # Convert to dictionary format for requests
                        for cookie in cookies_json:
                            name = cookie.get('name')
                            value = cookie.get('value')
                            if name and value:
                                cookies_dict[name] = value
                    else:
                        logger.debug("Cookie file exists but is empty")
                except Exception as e:
                    logger.error(f"Error loading Twitter cookies: {str(e)}")
            else:
                logger.debug("No Twitter cookies file found. Create one using twitter_cookie_tool.py")
            
            loop = asyncio.get_event_loop()
            scraper = self.scraper if hasattr(self, 'scraper') else cloudscraper.create_scraper()
            response = await loop.run_in_executor(
                None, 
                lambda: scraper.get(
                    twitter_url, 
                    cookies=cookies_dict if cookies_dict else None,
                    headers=headers,
                    timeout=15
                )
            )
            
            if response.status_code == 200:
                html = response.text
                logger.debug("Successfully fetched Twitter HTML")
                
                # Check if hit a login wall despite cookies
                login_indicators = ["Log in", "login form", "password", "Sign in", "Sign up", "Create account", "to X to see"]
                if any(indicator in html for indicator in login_indicators) and cookies_dict:
                    logger.warning("Hit Twitter login wall despite cookies - possibly expired cookies")
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Method 1: Try to extract from meta tags
                og_title = soup.select_one('meta[property="og:title"]')
                if og_title and og_title.get('content'):
                    title_content = og_title.get('content', '')
                    # Extract name from pattern like "Username on X/Twitter: "text" / X/Twitter"
                    title_match = re.search(r'^([^(]+?)\s+on\s+(?:X|Twitter)', title_content)
                    if title_match:
                        username = title_match.group(1).strip()
                        logger.info(f"Extracted Twitter username from og:title: {username}")
                        return username
                
                # Method 2: Try to find in canonical link
                canonical = soup.select_one('link[rel="canonical"]')
                if canonical and canonical.get('href'):
                    href = canonical.get('href', '')
                    canonical_match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)/status/', href)
                    if canonical_match:
                        username = canonical_match.group(1)
                        if username != "user":
                            logger.info(f"Extracted Twitter username from canonical URL: {username}")
                            return username
                
                # Method 3: Try to find author links
                author_tags = soup.select('a[data-testid*="author"], a[data-testid*="user"]')
                for tag in author_tags:
                    href = tag.get('href', '')
                    if href and href.startswith('/'):
                        segments = href.split('/')
                        if len(segments) >= 2 and segments[1] and segments[1] not in ['search', 'settings', 'i']:
                            username = segments[1]
                            logger.info(f"Extracted Twitter username from author link: {username}")
                            return username
                
                # Method 4: Try to extract from JSON content in script tags
                script_tags = soup.select('script[type="application/json"]')
                for script in script_tags:
                    content = script.string
                    if content:
                        try:
                            json_data = json.loads(content)
                            # Search for "screen_name" or "username" in JSON recursively
                            def find_username_in_json(obj):
                                if isinstance(obj, dict):
                                    if 'screen_name' in obj:
                                        return obj['screen_name']
                                    if 'username' in obj:
                                        return obj['username']
                                    for key, value in obj.items():
                                        result = find_username_in_json(value)
                                        if result:
                                            return result
                                elif isinstance(obj, list):
                                    for item in obj:
                                        result = find_username_in_json(item)
                                        if result:
                                            return result
                                return None
                                
                            username = find_username_in_json(json_data)
                            if username:
                                logger.info(f"Extracted Twitter username from JSON data: {username}")
                                return username
                        except Exception as json_error:
                            logger.debug(f"Error parsing JSON script: {str(json_error)}")
                
                # Method 5: Fall back to regex on the HTML
                username_patterns = [
                    r'"screen_name":"([^"]+)"',
                    r'"username":"([^"]+)"',
                    r'@([a-zA-Z0-9_]+)\s+on\s+(?:X|Twitter)'
                ]
                
                for pattern in username_patterns:
                    matches = re.findall(pattern, html)
                    if matches:
                        for match in matches:
                            # Skip common UI elements that might match
                            if match.lower() in ['search', 'home', 'explore', 'notifications', 'messages', 'bookmarks']:
                                continue
                            logger.info(f"Extracted Twitter username using regex: {match}")
                            return match
            else:
                logger.warning(f"Failed to fetch Twitter page. Status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching Twitter HTML: {str(e)}", exc_info=True)
        
        # Try to extract from URL one last time
        if username_from_url and username_from_url not in ["i", "search", "home", "explore", "notifications", "messages"]:
            logger.info(f"Falling back to username from URL: {username_from_url}")
            return username_from_url
            
        # No username could be extracted
        return ""
        
    async def _extract_bluesky_username(self, url: str) -> str:
        """Extract username from Bluesky URL with robust fallbacks"""
        # Try Selenium approach first
        try:
            logger.debug(f"Attempting to extract Bluesky username using Selenium from {url}")
            username = await self._extract_bluesky_username_with_selenium(url)
            if username:
                logger.info(f"Successfully extracted Bluesky username with Selenium: {username}")
                return username
        except Exception as selenium_error:
            logger.error(f"Selenium extraction for Bluesky failed: {str(selenium_error)}")
            
        # Fallback to direct URL parsing if Selenium fails
        logger.debug(f"Selenium extraction failed for Bluesky, falling back to URL extraction: {url}")
        
        # Extract username from URL
        username_match = re.search(r'bsky\.app/profile/([^/]+)', url.lower())
        if username_match:
            username = username_match.group(1)
            logger.info(f"Extracted Bluesky username from URL: {username}")
            return username
            
        # Extract from post URL - posts have author info in the URL
        post_match = re.search(r'bsky\.app/profile/([^/]+)/post', url.lower())
        if post_match:
            username = post_match.group(1)
            logger.info(f"Extracted Bluesky username from post URL: {username}")
            return username
            
        # Fallback to cloudscraper if direct URL parsing fails
        logger.debug(f"URL extraction failed, trying cloudscraper for {url}")
        
        # Create a cloudscraper instance if we don't already have one
        if not hasattr(self, 'scraper') or self.scraper is None:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                },
                debug=False
            )
        
        try:
            # Set up headers to look more like a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://bsky.app/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Try to find cookie files in multiple locations
            cookie_paths = [
                os.path.join(os.path.dirname(__file__), 'bluesky_cookies.json'),  # Same directory
                os.path.join(os.path.dirname(__file__), 'cookies', 'bluesky_cookies.json'),  # Cookies subdirectory
                'bluesky_cookies.json',  # Root directory
                os.path.join('cookies', 'bluesky_cookies.json')  # Cookies subdirectory from root
            ]
            
            cookies = {}
            cookie_file = None
            for path in cookie_paths:
                if os.path.exists(path):
                    cookie_file = path
                    logger.debug(f"Found Bluesky cookies at: {path}")
                    break
                    
            if cookie_file:
                try:
                    with open(cookie_file, 'r') as f:
                        stored_cookies = json.load(f)
                        
                    if stored_cookies:
                        logger.debug(f"Loading {len(stored_cookies)} Bluesky cookies from {cookie_file}")
                        for cookie in stored_cookies:
                            if 'name' in cookie and 'value' in cookie:
                                cookies[cookie['name']] = cookie['value']
                        logger.debug(f"Converted {len(cookies)} Bluesky cookies to dictionary format")
                except Exception as cookie_error:
                    logger.error(f"Error loading Bluesky cookies: {str(cookie_error)}")
            
            # Try to fetch the page with cloudscraper
            logger.debug(f"Fetching Bluesky page from {url} using cloudscraper")
            response = self.scraper.get(url, headers=headers, cookies=cookies)
            
            if response.status_code == 200:
                logger.debug("Successfully fetched Bluesky page HTML")
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Method 1: Try to find the display name and username in title
                title_tag = soup.find('title')
                if title_tag and title_tag.string:
                    title_text = title_tag.string
                    title_match = re.search(r'(@[a-zA-Z0-9_.]+)', title_text)
                    if title_match:
                        username = title_match.group(1)[1:]  # Remove the @ symbol
                        logger.info(f"Extracted Bluesky username from page title: {username}")
                        return username
                
                # Method 2: Try to find meta tags with author information
                meta_tags = soup.find_all('meta')
                for meta in meta_tags:
                    if meta.get('property') == 'og:title' or meta.get('name') == 'twitter:title':
                        content = meta.get('content', '')
                        title_match = re.search(r'(@[a-zA-Z0-9_.]+)', content)
                        if title_match:
                            username = title_match.group(1)[1:]  # Remove the @ symbol
                            logger.info(f"Extracted Bluesky username from meta tag: {username}")
                            return username
                
                # Method 3: Try to find any handle in the HTML
                username_tags = re.findall(r'@([a-zA-Z0-9_.]+)\.bsky\.social', response.text)
                if username_tags:
                    username = username_tags[0]
                    logger.info(f"Extracted Bluesky username from HTML content: {username}")
                    return username
            else:
                logger.error(f"Failed to fetch Bluesky page: HTTP {response.status_code}")
                
        except Exception as scraper_error:
            logger.error(f"Error using cloudscraper for Bluesky: {str(scraper_error)}")
            
        # If all methods fail, return empty string
        logger.warning(f"All methods failed to extract Bluesky username from {url}")
        return ""
        
    async def _extract_furaffinity_username_with_selenium(self, url: str) -> str:
        """
        Use Selenium with headless Chrome to extract FurAffinity username with cookie support
        This method handles JavaScript-rendered content and can use cookies to bypass login walls
        
        Note: This method is optimized for environments with resource constraints (like Replit)
        with proper fallbacks to non-Selenium methods when necessary.
        """
        try:
            # Setup Chrome options for headless operation
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Set up a user agent that looks like a regular browser
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
            
            # Create headless browser
            driver = webdriver.Chrome(options=chrome_options)
            
            # Set timeouts to avoid hanging
            driver.set_page_load_timeout(20)
            driver.set_script_timeout(20)
            
            try:
                # Check for cookie files in multiple locations
                cookie_paths = [
                    os.path.join(os.path.dirname(__file__), 'furaffinity_cookies.json'),  # Same directory
                    os.path.join(os.path.dirname(__file__), 'cookies', 'furaffinity_cookies.json'),  # Cookies subdirectory
                    'furaffinity_cookies.json',  # Root directory
                    os.path.join('cookies', 'furaffinity_cookies.json')  # Cookies subdirectory from root
                ]
                
                cookie_file = None
                for path in cookie_paths:
                    if os.path.exists(path):
                        cookie_file = path
                        logger.debug(f"Found FurAffinity cookies for Selenium at: {path}")
                        break
                
                # First just navigate to the main site to set up cookies domain
                driver.get("https://www.furaffinity.net")
                
                # Load cookies if available
                if cookie_file:
                    try:
                        with open(cookie_file, 'r') as f:
                            cookies = json.load(f)
                        
                        if cookies:
                            logger.debug(f"Loading {len(cookies)} FurAffinity cookies for Selenium")
                            for cookie in cookies:
                                # Make sure cookie has all required fields for Selenium
                                if 'name' in cookie and 'value' in cookie:
                                    # Create a clean cookie dict with only the required fields
                                    cookie_dict = {
                                        'name': cookie['name'],
                                        'value': cookie['value'],
                                        'domain': '.furaffinity.net',
                                        'path': '/'
                                    }
                                    
                                    # Optional fields that Selenium accepts
                                    if 'expiry' in cookie and cookie['expiry']:
                                        try:
                                            # Ensure expiry is an integer timestamp
                                            cookie_dict['expiry'] = int(cookie['expiry'])
                                        except (ValueError, TypeError):
                                            # Skip if we can't convert it
                                            pass
                                    
                                    # Add cookie to browser
                                    try:
                                        driver.add_cookie(cookie_dict)
                                        logger.debug(f"Added cookie: {cookie['name']}")
                                    except Exception as cookie_error:
                                        logger.debug(f"Error adding cookie {cookie['name']}: {str(cookie_error)}")
                    except Exception as e:
                        logger.error(f"Error loading cookies for Selenium: {str(e)}")
                
                # Now navigate to the actual URL
                driver.get(url)
                
                # Wait for the page to load essential content
                logger.debug("Waiting for FurAffinity page to load using Selenium...")
                
                # First, try the iconusername
                try:
                    username_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.iconusername"))
                    )
                    username = username_element.text.strip()
                    if username:
                        logger.info(f"Extracted FurAffinity username with Selenium (iconusername): {username}")
                        return username
                except Exception:
                    logger.debug("Could not find iconusername with Selenium")
                
                # Then try the author link
                try:
                    author_element = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.author"))
                    )
                    username = author_element.text.strip()
                    if username:
                        logger.info(f"Extracted FurAffinity username with Selenium (author): {username}")
                        return username
                except Exception:
                    logger.debug("Could not find author link with Selenium")
                
                # Look in submission-author
                try:
                    container = driver.find_element(By.ID, "submission-author")
                    if container:
                        links = container.find_elements(By.TAG_NAME, "a")
                        if links:
                            username = links[0].text.strip()
                            if username:
                                logger.info(f"Extracted FurAffinity username with Selenium (submission-author): {username}")
                                return username
                except Exception:
                    logger.debug("Could not find submission-author with Selenium")
                
                # Try extracting from title
                title = driver.title
                if title:
                    username = self._extract_from_title(title)
                    if username:
                        logger.info(f"Extracted FurAffinity username from title: {username}")
                        return username
                
                # Try extracting from meta tags
                username = self._extract_from_meta(driver)
                if username:
                    logger.info(f"Extracted FurAffinity username from meta tags: {username}")
                    return username
                
                # Try extracting from user links
                username = self._extract_from_elements(driver, By.CSS_SELECTOR, "a[href^='/user/']")
                if username:
                    logger.info(f"Extracted FurAffinity username from user links: {username}")
                    return username
                
                # If we got here, we couldn't find a username with Selenium
                logger.debug("Could not extract FurAffinity username with Selenium")
                    
            finally:
                # Always close the driver to free resources
                try:
                    driver.quit()
                except Exception as quit_error:
                    logger.error(f"Error closing Selenium driver: {str(quit_error)}")
                    
        except Exception as selenium_error:
            logger.error(f"Selenium error for FurAffinity: {str(selenium_error)}")
            
        return ""
        
    async def _extract_bluesky_username_with_selenium(self, url: str) -> str:
        """
        Use Selenium with headless Chrome to extract Bluesky username with cookie support
        This method handles JavaScript-rendered content and can use cookies to bypass login
        """
        try:
            # Setup Chrome options for headless operation
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Set up a user agent that looks like a regular browser
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
            
            # Create headless browser
            driver = webdriver.Chrome(options=chrome_options)
            
            # Set timeouts to avoid hanging
            driver.set_page_load_timeout(20)
            driver.set_script_timeout(20)
            
            try:
                # Check for cookie files in multiple locations
                cookie_paths = [
                    os.path.join(os.path.dirname(__file__), 'bluesky_cookies.json'),  # Same directory
                    os.path.join(os.path.dirname(__file__), 'cookies', 'bluesky_cookies.json'),  # Cookies subdirectory
                    'bluesky_cookies.json',  # Root directory
                    os.path.join('cookies', 'bluesky_cookies.json')  # Cookies subdirectory from root
                ]
                
                cookie_file = None
                for path in cookie_paths:
                    if os.path.exists(path):
                        cookie_file = path
                        logger.debug(f"Found Bluesky cookies for Selenium at: {path}")
                        break
                
                # First navigate to the main site to set up cookies domain
                driver.get("https://bsky.app")
                
                # Load cookies if available
                if cookie_file:
                    try:
                        with open(cookie_file, 'r') as f:
                            cookies = json.load(f)
                        
                        if cookies:
                            logger.debug(f"Loading {len(cookies)} Bluesky cookies for Selenium")
                            for cookie in cookies:
                                # Make sure cookie has all required fields for Selenium
                                if 'name' in cookie and 'value' in cookie:
                                    # Create a clean cookie dict with only the required fields
                                    cookie_dict = {
                                        'name': cookie['name'],
                                        'value': cookie['value'],
                                        'domain': '.bsky.app',
                                        'path': '/'
                                    }
                                    
                                    # Optional fields that Selenium accepts
                                    if 'expiry' in cookie and cookie['expiry']:
                                        try:
                                            # Ensure expiry is an integer timestamp
                                            cookie_dict['expiry'] = int(cookie['expiry'])
                                        except (ValueError, TypeError):
                                            # Skip if we can't convert it
                                            pass
                                    
                                    # Add cookie to browser
                                    try:
                                        driver.add_cookie(cookie_dict)
                                        logger.debug(f"Added cookie: {cookie['name']}")
                                    except Exception as cookie_error:
                                        logger.debug(f"Error adding cookie {cookie['name']}: {str(cookie_error)}")
                    except Exception as e:
                        logger.error(f"Error loading cookies for Selenium: {str(e)}")
                
                # Now navigate to the actual URL
                driver.get(url)
                
                # Wait for the page to load essential content
                logger.debug("Waiting for Bluesky page to load using Selenium...")
                time.sleep(3)  # Give time for JavaScript to execute
                
                # Method 1: Look for username in title
                title = driver.title
                if title:
                    # Look for patterns like "Post by @username"
                    title_match = re.search(r'by\s+@([a-zA-Z0-9_.]+)', title)
                    if title_match:
                        username = title_match.group(1)
                        logger.info(f"Extracted Bluesky username from title: {username}")
                        return username
                
                # Method 2: Look for user header with handle
                try:
                    # Try to find the user handle element
                    handle_elements = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="profileHeaderHandle"]')
                    if handle_elements:
                        for element in handle_elements:
                            handle_text = element.text.strip()
                            if handle_text.startswith('@'):
                                username = handle_text[1:] # Remove @ symbol
                                logger.info(f"Extracted Bluesky username from header handle: {username}")
                                return username
                except Exception as element_error:
                    logger.debug(f"Error finding handle elements: {str(element_error)}")
                
                # Method 3: Look for profile display name in header
                try:
                    name_elements = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="profileDisplayName"]')
                    if name_elements:
                        # Look for the handle which is usually near the display name
                        for element in name_elements:
                            # Try to get parent element and find handle
                            parent = element.find_element(By.XPATH, './..')
                            handle_element = parent.find_element(By.CSS_SELECTOR, '*[data-testid="profileHeaderHandle"]')
                            if handle_element:
                                handle_text = handle_element.text.strip()
                                if handle_text.startswith('@'):
                                    username = handle_text[1:]  # Remove @ symbol
                                    logger.info(f"Extracted Bluesky username from display name section: {username}")
                                    return username
                except Exception as name_error:
                    logger.debug(f"Error finding name elements: {str(name_error)}")
                
                # Method 4: Look for .bsky.social in any text
                try:
                    page_source = driver.page_source
                    handle_matches = re.findall(r'@([a-zA-Z0-9_.]+)\.bsky\.social', page_source)
                    if handle_matches:
                        username = handle_matches[0]
                        logger.info(f"Extracted Bluesky username from page source: {username}")
                        return username
                except Exception as source_error:
                    logger.debug(f"Error searching page source: {str(source_error)}")
                
                # Method 5: Extract from any href attribute that looks like a profile
                try:
                    profile_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/profile/"]')
                    for link in profile_links:
                        href = link.get_attribute('href')
                        if href:
                            # Extract username from profile URL
                            profile_match = re.search(r'/profile/([^/]+)', href)
                            if profile_match:
                                did_or_handle = profile_match.group(1)
                                if not did_or_handle.startswith('did:'):
                                    logger.info(f"Extracted Bluesky username from profile link: {did_or_handle}")
                                    return did_or_handle
                except Exception as link_error:
                    logger.debug(f"Error finding profile links: {str(link_error)}")
                
                # If we got here, we couldn't find a username with Selenium
                logger.debug("Could not extract Bluesky username with Selenium")
            
            finally:
                # Always close the driver to free resources
                try:
                    driver.quit()
                except Exception as quit_error:
                    logger.error(f"Error closing Selenium driver: {str(quit_error)}")
        
        except Exception as selenium_error:
            logger.error(f"Selenium error for Bluesky: {str(selenium_error)}")
        
        return ""
        
    async def _extract_twitter_username_with_selenium(self, url: str) -> str:
        """
        Use Selenium with headless Chrome to extract Twitter username with cookie support
        This method handles JavaScript-rendered content and can use cookies to bypass login
        """
        try:
            # Setup Chrome options for headless operation
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Set up a user agent that looks like a regular browser
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
            
            # Create headless browser
            driver = webdriver.Chrome(options=chrome_options)
            
            # Set timeouts to avoid hanging
            driver.set_page_load_timeout(20)
            driver.set_script_timeout(20)
            
            try:
                # Check for cookie files in multiple locations
                cookie_paths = [
                    os.path.join(os.path.dirname(__file__), 'twitter_cookies.json'),  # Same directory
                    os.path.join(os.path.dirname(__file__), 'cookies', 'twitter_cookies.json'),  # Cookies subdirectory
                    'twitter_cookies.json',  # Root directory
                    os.path.join('cookies', 'twitter_cookies.json')  # Cookies subdirectory from root
                ]
                
                cookie_file = None
                for path in cookie_paths:
                    if os.path.exists(path):
                        cookie_file = path
                        logger.debug(f"Found Twitter cookies for Selenium at: {path}")
                        break
                
                # First navigate to the main site to set up cookies domain
                driver.get("https://twitter.com")
                
                # Load cookies if available
                if cookie_file:
                    try:
                        with open(cookie_file, 'r') as f:
                            cookies = json.load(f)
                        
                        if cookies:
                            logger.debug(f"Loading {len(cookies)} Twitter cookies for Selenium")
                            
                            # Determine the correct domain suffix
                            domain_suffix = '.twitter.com' if 'twitter.com' in url else '.x.com'
                            
                            for cookie in cookies:
                                # Make sure cookie has all required fields for Selenium
                                if 'name' in cookie and 'value' in cookie:
                                    # Create a clean cookie dict with only the required fields
                                    cookie_dict = {
                                        'name': cookie['name'],
                                        'value': cookie['value'],
                                        'domain': domain_suffix,
                                        'path': '/'
                                    }
                                    
                                    # Optional fields that Selenium accepts
                                    if 'expiry' in cookie and cookie['expiry']:
                                        try:
                                            # Ensure expiry is an integer timestamp
                                            cookie_dict['expiry'] = int(cookie['expiry'])
                                        except (ValueError, TypeError):
                                            # Skip if we can't convert it
                                            pass
                                            
                                    # Add cookie to browser
                                    try:
                                        driver.add_cookie(cookie_dict)
                                        logger.debug(f"Added cookie: {cookie['name']}")
                                    except Exception as cookie_error:
                                        logger.debug(f"Error adding cookie {cookie['name']}: {str(cookie_error)}")
                    except Exception as e:
                        logger.error(f"Error loading cookies for Selenium: {str(e)}")
                
                # Now navigate to the actual URL
                driver.get(url)
                
                # Wait for the page to load essential content
                logger.debug("Waiting for Twitter page to load using Selenium...")
                
                # Let JavaScript execute and try to find author name in various patterns
                time.sleep(3)  # Give a few seconds for JavaScript to execute
                
                # Method 1: Extract from title
                title = driver.title
                if title:
                    # Look for patterns like "Username on X: "text""
                    title_match = re.search(r'^([^(]+?)\s+on\s+(?:X|Twitter)', title)
                    if title_match:
                        username = title_match.group(1).strip()
                        logger.info(f"Extracted Twitter username from title: {username}")
                        return username
                
                # Method 2: Extract from user links
                try:
                    # Twitter data-testid attributes
                    username_elements = driver.find_elements(By.CSS_SELECTOR, '[data-testid="User-Name"]')
                    for element in username_elements:
                        # Try to get the username text
                        try:
                            # Username header div sometimes contains username (with @) as a span
                            spans = element.find_elements(By.TAG_NAME, "span")
                            for span in spans:
                                span_text = span.text
                                if span_text and span_text.startswith('@'):
                                    username = span_text[1:]  # Remove the @ symbol
                                    logger.info(f"Extracted Twitter username from User-Name spans: {username}")
                                    return username
                        except Exception:
                            pass
                except Exception as element_error:
                    logger.debug(f"Error finding User-Name elements: {str(element_error)}")
                
                # Method 3: Look for tweet author section
                try:
                    # Other patterns to try
                    username_elements = driver.find_elements(By.CSS_SELECTOR, 'a[href^="/"], a[role="link"]')
                    for element in username_elements:
                        href = element.get_attribute('href')
                        if href:
                            href_lower = href.lower()
                            if 'twitter.com/' in href_lower or 'x.com/' in href_lower:
                                # Extract username from URL
                                username_match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)$', href_lower)
                                if username_match:
                                    username = username_match.group(1)
                                    # Skip common Twitter UI elements
                                    if username not in ['home', 'explore', 'notifications', 'messages', 'settings', 'i']:
                                        logger.info(f"Extracted Twitter username from href: {username}")
                                        return username
                except Exception as link_error:
                    logger.debug(f"Error finding link elements: {str(link_error)}")
                
                # Method 4: Try to parse any JSON data in scripts
                try:
                    script_elements = driver.find_elements(By.TAG_NAME, "script")
                    for script in script_elements:
                        content = script.get_attribute('innerHTML')
                        if content and '"screen_name":"' in content:
                            screen_name_match = re.search(r'"screen_name":"([^"]+)"', content)
                            if screen_name_match:
                                username = screen_name_match.group(1)
                                logger.info(f"Extracted Twitter username from script JSON: {username}")
                                return username
                except Exception as script_error:
                    logger.debug(f"Error parsing scripts: {str(script_error)}")
                
                # If we got here, we couldn't find a username with Selenium
                logger.debug("Could not extract Twitter username with Selenium")
                    
            finally:
                # Always close the driver to free resources
                try:
                    driver.quit()
                except Exception as quit_error:
                    logger.error(f"Error closing Selenium driver: {str(quit_error)}")
                    
        except Exception as selenium_error:
            logger.error(f"Selenium error for Twitter: {str(selenium_error)}")
            
        return ""
        
    def _extract_from_title(self, title: str) -> str:
        """Extract username from page title"""
        # FurAffinity pattern: "Title by Username -- Fur Affinity"
        furaffinity_match = re.search(r'\s+by\s+([^\s-]+)\s+--\s+Fur\s+Affinity', title)
        if furaffinity_match:
            return furaffinity_match.group(1)
            
        # Twitter pattern: "Username on X/Twitter: "Text""
        twitter_match = re.search(r'^([^(]+?)\s+on\s+(?:X|Twitter)', title)
        if twitter_match:
            return twitter_match.group(1).strip()
            
        return ""
        
    def _extract_from_elements(self, driver, by, selector: str) -> str:
        """Extract username from selected elements"""
        try:
            elements = driver.find_elements(by, selector)
            for element in elements:
                href = element.get_attribute('href')
                if href:
                    # FurAffinity pattern: /user/Username
                    furaffinity_match = re.search(r'/user/([a-zA-Z0-9_-]+)', href)
                    if furaffinity_match:
                        return furaffinity_match.group(1)
                        
                    # Twitter pattern: twitter.com/Username
                    twitter_match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)$', href)
                    if twitter_match:
                        username = twitter_match.group(1)
                        if username not in ['home', 'explore', 'notifications', 'messages', 'settings', 'i']:
                            return username
        except Exception as e:
            logger.debug(f"Error extracting from elements: {str(e)}")
            
        return ""
        
    def _extract_from_meta(self, driver) -> str:
        """Extract username from meta tags"""
        try:
            meta_elements = driver.find_elements(By.TAG_NAME, "meta")
            for meta in meta_elements:
                # Check for author meta tag
                if meta.get_attribute('name') == 'author':
                    return meta.get_attribute('content')
                    
                # Check for Twitter card creator
                if meta.get_attribute('name') == 'twitter:creator':
                    creator = meta.get_attribute('content')
                    if creator.startswith('@'):
                        return creator[1:]  # Remove the @ symbol
                    return creator
                    
                # Check for og:title with author pattern
                if meta.get_attribute('property') == 'og:title':
                    title = meta.get_attribute('content')
                    if title:
                        # FurAffinity pattern: "Title by Username"
                        fa_match = re.search(r'\s+by\s+([^\s]+)', title)
                        if fa_match:
                            return fa_match.group(1)
                            
                        # Twitter pattern: "Username on X/Twitter: "Text""
                        twitter_match = re.search(r'^([^(]+?)\s+on\s+(?:X|Twitter)', title)
                        if twitter_match:
                            return twitter_match.group(1).strip()
        except Exception as e:
            logger.debug(f"Error extracting from meta tags: {str(e)}")
            
        return ""
        
    async def cleanup(self):
        """Cleanup resources"""
        await self.mtproto_client.disconnect()