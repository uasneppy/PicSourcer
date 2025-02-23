import os
import io
import aiohttp
from typing import Optional
from PIL import Image
from logger import logger
from config import MAX_FILE_SIZE

async def download_image(file_id: str, bot) -> Optional[bytes]:
    """
    Download and process image from Telegram servers
    Returns image data optimized for photo sending
    """
    try:
        file = await bot.get_file(file_id)

        if file.file_size > MAX_FILE_SIZE:
            logger.warning(f"File size {file.file_size} exceeds maximum allowed size")
            return None

        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as response:
                if response.status == 200:
                    # Read image data
                    image_data = await response.read()

                    # Process image using PIL
                    image = Image.open(io.BytesIO(image_data))

                    # Convert to RGB if necessary (handles PNG with alpha channel)
                    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        if image.mode == 'P':
                            image = image.convert('RGBA')
                        background.paste(image, mask=image.split()[-1])
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')

                    # Resize if the image is too large
                    max_dimension = 4096  # Telegram's maximum image dimension
                    if max(image.size) > max_dimension:
                        ratio = max_dimension / max(image.size)
                        new_size = tuple(int(dim * ratio) for dim in image.size)
                        image = image.resize(new_size, Image.Resampling.LANCZOS)

                    # Save as JPEG in memory with high quality
                    output = io.BytesIO()
                    image.save(output, format='JPEG', quality=95, optimize=True)
                    output.seek(0)

                    logger.debug("Image successfully processed for photo sending")
                    return output.read()
                else:
                    logger.error(f"Failed to download image: {response.status}")
                    return None

    except Exception as e:
        logger.error(f"Error downloading/processing image: {str(e)}")
        return None