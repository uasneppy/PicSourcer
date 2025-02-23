import logging
from logging.handlers import RotatingFileHandler
from config import LOG_LEVEL, LOG_FORMAT

def setup_logger():
    # Create logger
    logger = logging.getLogger('SourceBot')
    logger.setLevel(getattr(logging, LOG_LEVEL))

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    console_formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(console_formatter)

    # Create file handler
    file_handler = RotatingFileHandler(
        'bot.log',
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, LOG_LEVEL))
    file_formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(file_formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
