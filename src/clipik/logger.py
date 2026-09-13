import os
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger
from clipik.config import Config


def initialize_logger(config: Config) -> None:
    global logger

    if os.name == 'nt': # Windows
        base_dir = Path(os.getenv('APPDATA', '~'))
    elif sys.platform == 'darwin': # macOS
        base_dir = Path.home() / 'Library' / 'Application Support'
    else: # Linux / Unix
        xdg = os.getenv('XDG_DATA_HOME')

        if xdg:
            base_dir = Path(xdg) / 'clipik'
        else:
            base_dir = Path.home() / '.local' / 'share'

    base_dir = base_dir / 'clipik'
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    filepath = base_dir / filename

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
