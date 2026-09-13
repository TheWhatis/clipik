import socket
from typing import TYPE_CHECKING
from websockets import ServerConnection
from clipik.enum import GraphicProtocol
from clipik.types import SetClipboardFn, ListenClipboardFn, IsDuplicateClipboardFn
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
    is_duplicate_clipboard: IsDuplicateClipboardFn
    required_utils: list[str] = []
    clients: set[ServerConnection] = set()

    def __init__(
        self,
        config: "Config",
        set_clipboard: SetClipboardFn,
        listen_clipboard: ListenClipboardFn,
        is_duplicate_clipboard: IsDuplicateClipboardFn,
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
        self.is_duplicate_clipboard = is_duplicate_clipboard

        required_utils: list[str] = []

        if config.graphic_protocol == GraphicProtocol.WAYLAND:
            required_utils = required_utils + [
                'wl-paste',
                'wl-copy',
            ]
        else:
            required_utils = required_utils + [
                'xclip',
                'clipnotify'
            ]

        self.required_utils = required_utils

    def raise_required_utils_is_needed(self):
        skipped_utils: list[str] = []

        for util in app.required_utils:
            if shutil.which(util) is None:
                skipped_utils.append(util)

        skipped_utils

        if skipped_utils:
            skipped_utils_str: str = ', '.join(skipped_utils)
            raise InitializationError(f'Utils [{skipped_utils_str}] is required, install it')
