import os
from clipik.logger import logger


PROTOCOL = 'CLIPIK'
VERSION = '0.1.19'
GRAPHIC_PROTOCOL = 'x11'

if os.getenv('WAYLAND_DISPLAY'):
    GRAPHIC_PROTOCOL = 'wayland'

logger.info('GRAPHIC_PROTOCOL is [{}]', GRAPHIC_PROTOCOL)


PEER_PORT = int(os.getenv('CLIPIK_PORT', default=8765))
logger.info('PORT: [{}]', PEER_PORT)


SIZE_LIMIT=int(os.getenv('CLIPIK_SIZE_LIMIT', default=64 * 1024 * 1024))
logger.info('SIZE_LIMIT: [{}]', SIZE_LIMIT)


REQUIRED_UTILS: list[str] = []

if GRAPHIC_PROTOCOL == 'wayland':
    REQUIRED_UTILS = REQUIRED_UTILS + [
        'wl-paste',
        'wl-copy',
    ]
else:
    REQUIRED_UTILS = REQUIRED_UTILS + [
        'xclip',
        'clipnotify'
    ]
