import os
import shutil
import socket
from typing import TYPE_CHECKING
from websockets import ServerConnection
from clipik.types import SetClipboardFn, ListenClipboardFn
from clipik.exception import InitializationError
from clipik.zeroconf import get_zeroconf


if TYPE_CHECKING:
    from zeroconf import Zeroconf
    from clipik.model import Config


class Container:
    program: str = 'clipik'
    protocol: str = 'CLIPIK'
    version: str = '0.3.0'

    service_name: str
    service_type: str = '_clipik._tcp.local.'
    local_ip: str
    zeroconf: "Zeroconf"

    config: "Config"
    set_clipboard: SetClipboardFn
    listen_clipboard: ListenClipboardFn
    required_utils: list[str] = []
    clients: set[ServerConnection] = set()

    def __init__(
        self,
        config: "Config",
        set_clipboard: SetClipboardFn,
        listen_clipboard: ListenClipboardFn,
    ):
        self.service_name = f"clipik-{socket.gethostname()}"

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        self.local_ip = s.getsockname()[0]
        s.close()

        self.zeroconf = get_zeroconf(self.local_ip)

        self.config = config
        self.set_clipboard = set_clipboard
        self.listen_clipboard = listen_clipboard

        required_utils: list[str] = []

        if os.getenv('WAYLAND_DISPLAY', default=None):
            required_utils = required_utils + [
                'wl-paste',
                'wl-copy',
            ]

        required_utils = required_utils + [
            'xclip',
            'clipnotify',
        ]

        self.required_utils = required_utils
        self.raise_required_utils_is_needed()

    def raise_required_utils_is_needed(self):
        skipped_utils: list[str] = []

        for util in self.required_utils:
            if shutil.which(util) is None:
                skipped_utils.append(util)

        if skipped_utils:
            skipped_utils_str: str = ', '.join(skipped_utils)
            raise InitializationError(f'Utils [{skipped_utils_str}] is required, install it')
