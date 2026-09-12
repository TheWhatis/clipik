import os
from clipik.logger import logger


PROTOCOL = 'CLIPIK'
VERSION = '0.1.18'
GRAPHIC_PROTOCOL = 'x11'

if os.getenv('WAYLAND_DISPLAY'):
    GRAPHIC_PROTOCOL = 'wayland'


logger.info('GRAPHIC_PROTOCOL is [{}]', GRAPHIC_PROTOCOL)


PEER_PORT = os.getenv('CLIPIK_PORT', default=8765)
PEER_PORT = int(PEER_PORT)


logger.info('PORT: [{}]', PEER_PORT)


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
