import asyncio
import io
import re
from typing import Optional, Dict, List

import aiohttp
from PIL import Image

from config import (
    FLUFFLE_API_URL,
    FLUFFLE_USER_AGENT,
    FLUFFLE_INCLUDE_NSFW,
    FLUFFLE_LIMIT,
    FLUFFLE_PLATFORMS,
    FLUFFLE_TIMEOUT,
    FLUFFLE_MAX_DIMENSION,
    MATCH_ORDER,
    ACCEPTED_MATCHES,
    PLATFORM_PRIORITY,
    PLATFORM_DISPLAY_NAMES,
    META_ARTIST_TAGS,
)
from logger import logger


def _normalize_platform(platform: str) -> str:
    """Reduce a platform name to lowercase-alphanumeric for robust matching.

    Fluffle returns camelCase machine names ("furAffinity"); this makes lookups
    tolerant of casing/spacing ("Fur Affinity", "furaffinity", ... all match).
    """
    return re.sub(r"[^a-z0-9]", "", (platform or "").lower())

# Marker understood by bot.py: attribute a Bluesky post generically when Fluffle
# returns no artist credit for it (preserves the previous product behaviour).
BLUESKY_GENERIC_ATTRIBUTION = "BLUESKY_GENERIC_ATTRIBUTION"

# Minimum seconds between two Fluffle requests. Fluffle processes one request per
# client at a time, so we serialise and pace calls to stay well within budget.
_MIN_SEARCH_INTERVAL = 2.0

# Rank lookup for match tiers, keyed lowercase, e.g. {"exact": 0, "tossup": 1, ...}
_MATCH_RANK = {name.lower(): i for i, name in enumerate(MATCH_ORDER)}


class ImageSearcher:
    """Reverse-image searcher backed by the Fluffle API (https://fluffle.xyz).

    Replaces the previous pipeline that forwarded images to @FindFurryPicBot over
    MTProto and then scraped each source site (Selenium/cloudscraper) for the
    artist name. Fluffle returns the source URL, platform and artist credits
    directly, in a single request.

    The public surface — ``start()``, ``search_image()``, ``cleanup()`` and a
    result dict of ``{source_url, source_name, author_nickname}`` — is unchanged
    so the rest of the bot keeps working as-is.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        # Fluffle allows only one concurrent request per client; serialise here.
        self._lock = asyncio.Lock()
        self._last_search_time = 0.0
        logger.debug("ImageSearcher initialized (Fluffle backend)")

    async def start(self):
        """Create the shared HTTP session. Kept for bot lifecycle compatibility."""
        await self._get_session()
        logger.info("ImageSearcher ready (Fluffle backend)")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Fluffle requires a descriptive, identifiable User-Agent on every call.
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": FLUFFLE_USER_AGENT}
            )
        return self._session

    async def search_image(self, bot, image_data: bytes) -> Optional[Dict]:
        """Reverse-search an image via Fluffle and return the best source.

        Returns ``{"source_url", "source_name", "author_nickname"}`` or ``None``
        when no sufficiently confident match is found. ``bot`` is accepted for
        backwards compatibility with the previous call signature and is unused.
        """
        async with self._lock:
            # Basic client-side pacing between requests.
            now = asyncio.get_event_loop().time()
            gap = now - self._last_search_time
            if gap < _MIN_SEARCH_INTERVAL:
                await asyncio.sleep(_MIN_SEARCH_INTERVAL - gap)

            try:
                # Downscale/re-encode off the event loop (PIL is blocking).
                payload = await asyncio.get_event_loop().run_in_executor(
                    None, self._prepare_image, image_data
                )
                response = await self._query_fluffle(payload)
            except Exception as e:
                logger.error(f"Error during Fluffle image search: {e}", exc_info=True)
                response = None
            finally:
                self._last_search_time = asyncio.get_event_loop().time()

        if not response:
            return None

        results = response.get("results") or []
        logger.debug(f"Fluffle returned {len(results)} result(s)")

        best = self._select_best_result(results)
        if not best:
            logger.info("Fluffle found no sufficiently confident match")
            return None

        source_url = best.get("location", "")
        platform = best.get("platform", "")
        source_name = self._display_name(platform)
        author_nickname = self._extract_credits(best, platform)

        logger.info(
            f"Fluffle match: {source_name} (match={best.get('match')}, "
            f"score={best.get('score')}) -> {source_url}"
            + (f" by {author_nickname}" if author_nickname else "")
        )

        return {
            "source_url": source_url,
            "source_name": source_name,
            "author_nickname": author_nickname,
        }

    def _display_name(self, platform: str) -> str:
        """Human-readable platform name for captions (e.g. 'Fur Affinity')."""
        norm = _normalize_platform(platform)
        return PLATFORM_DISPLAY_NAMES.get(norm) or (platform or "Source")

    # ------------------------------------------------------------------ request

    async def _query_fluffle(self, image_data: bytes) -> Optional[dict]:
        """POST the image to Fluffle, retrying briefly on 429 / 5xx responses."""
        max_attempts = 3
        backoff = 2.0

        for attempt in range(1, max_attempts + 1):
            try:
                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    image_data,
                    filename="image.jpg",
                    content_type="image/jpeg",
                )
                form.add_field(
                    "includeNsfw", "true" if FLUFFLE_INCLUDE_NSFW else "false"
                )
                form.add_field("limit", str(FLUFFLE_LIMIT))
                # Repeated fields bind to Fluffle's string[] `platforms`. Omitting
                # them (empty list) searches every supported platform.
                for platform in FLUFFLE_PLATFORMS:
                    form.add_field("platforms", platform)

                session = await self._get_session()
                timeout = aiohttp.ClientTimeout(total=FLUFFLE_TIMEOUT)
                async with session.post(
                    FLUFFLE_API_URL, data=form, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()

                    body = (await resp.text())[:300]
                    if resp.status == 429:
                        logger.warning(
                            f"Fluffle rate-limited (429), attempt "
                            f"{attempt}/{max_attempts}"
                        )
                    elif resp.status in (500, 503):
                        logger.warning(
                            f"Fluffle unavailable ({resp.status}), attempt "
                            f"{attempt}/{max_attempts}: {body}"
                        )
                    else:
                        # 400/413/415/422 are client-side problems; don't retry.
                        logger.error(
                            f"Fluffle request failed ({resp.status}): {body}"
                        )
                        return None
            except asyncio.TimeoutError:
                logger.warning(
                    f"Fluffle request timed out, attempt {attempt}/{max_attempts}"
                )
            except aiohttp.ClientError as e:
                logger.warning(
                    f"Fluffle network error, attempt {attempt}/{max_attempts}: {e}"
                )

            if attempt < max_attempts:
                await asyncio.sleep(backoff)
                backoff *= 2

        logger.error("Fluffle request failed after retries")
        return None

    # ------------------------------------------------------------- result choice

    def _select_best_result(self, results: List[dict]) -> Optional[dict]:
        """Pick the most trustworthy result.

        Preference order: match confidence (exact > tossUp > ...), then platform
        priority (e621 first for the richest artist data), then Fluffle's score.
        """
        candidates = [
            r
            for r in results
            if r.get("location")
            and (r.get("match") or "").lower() in ACCEPTED_MATCHES
        ]
        if not candidates:
            return None

        def sort_key(r: dict):
            match_rank = _MATCH_RANK.get((r.get("match") or "").lower(), len(MATCH_ORDER))
            platform_rank = PLATFORM_PRIORITY.get(
                _normalize_platform(r.get("platform", "")), 99
            )
            score = r.get("score") or 0.0
            return (match_rank, platform_rank, -score)

        candidates.sort(key=sort_key)
        return candidates[0]

    # -------------------------------------------------------------- credits/name

    def _extract_credits(self, result: dict, platform: str) -> str:
        """Build an artist attribution string from Fluffle's ``credits`` array."""
        credits = result.get("credits") or []
        names: List[str] = []
        for credit in credits:
            name = (credit.get("name") or "").strip()
            if not name:
                continue
            # Strip e621's "_(artist)" suffix and drop non-artist meta tags.
            cleaned = re.sub(r"_\(artist\)$", "", name)
            if not cleaned or cleaned.lower() in META_ARTIST_TAGS:
                continue
            names.append(cleaned)

        if names:
            # De-duplicate while preserving order.
            return ", ".join(dict.fromkeys(names))

        # No artist credit: preserve the previous generic Bluesky attribution.
        if _normalize_platform(platform) == "bluesky":
            return BLUESKY_GENERIC_ATTRIBUTION
        return ""

    # ---------------------------------------------------------- image prep/util

    def _prepare_image(self, image_data: bytes) -> bytes:
        """Downscale / re-encode so the upload respects Fluffle's size limits."""
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.mode != "RGB":
                img = img.convert("RGB")

            longest = max(img.size)
            if longest > FLUFFLE_MAX_DIMENSION:
                ratio = FLUFFLE_MAX_DIMENSION / longest
                new_size = (
                    max(1, int(img.width * ratio)),
                    max(1, int(img.height * ratio)),
                )
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=90, optimize=True)
            return out.getvalue()
        except Exception as e:
            logger.warning(f"Image preprocessing failed, using original bytes: {e}")
            return image_data

    async def cleanup(self):
        """Close the shared HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("ImageSearcher cleaned up")
