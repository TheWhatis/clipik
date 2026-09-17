import os
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger
from .config import Config


def initialize_logger(config: Config) -> None:
    global logger
    config.log_dir.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    filepath = config.log_dir / filename

    logger.remove()

    logger.add(
        str(filepath),
        level=config.log_level,
        encoding='utf-8',
        rotation='10mb',
        compression='gz'
    )

    logger.add(
        sys.stdout,
        level=config.log_level,
        colorize=True
    )

    logger.add(
        sys.stderr,
        level='ERROR',
        colorize=True,
    )

    logger.info('Log level: [{}]',config.log_level)
    logger.info('Log file is [{}]', filepath)
