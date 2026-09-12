import os
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger


_level = os.getenv('CLIPIK_LOG_LEVEL', 'INFO')


if os.name == 'nt': # Windows
    _base_dir = Path(os.getenv('APPDATA', '~'))
elif sys.platform == 'darwin': # macOS
    _base_dir = Path.home() / 'Library' / 'Application Support'
else: # Linux / Unix
    xdg = os.getenv('XDG_DATA_HOME')

    if xdg:
        _base_dir = Path(xdg) / 'clipik'
    else:
        _base_dir = Path.home() / '.local' / 'share'


_base_dir = _base_dir / 'clipik'
_base_dir.mkdir(parents=True, exist_ok=True)

_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
_filepath = _base_dir / _filename


logger.remove()
logger.add(str(_filepath), level=_level, encoding='utf-8', rotation='10mb', compression='gz')
logger.add(sys.stdout, level=_level, colorize=True)

logger.info('ENV LOG_LEVEL: [{}]', _level)
