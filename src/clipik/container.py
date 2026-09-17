import os
import sys
import shutil
import socket
import getpass
import sqlite3
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING
from websockets import ServerConnection
from .types import (
    DiscoverServicesFn,
    SetClipboardFn,
    ListenClipboardFn,
    RegisterServiceFn,
    UnregisterServiceFn,
)
from .exception import InitializationError
from .functions import get_ips_by_interface, get_default_ip


if TYPE_CHECKING:
    from zeroconf import Zeroconf
    from .model import Config


def _resolve_version() -> str:
    try:
        return version('clipik')
    except PackageNotFoundError:
        pass

    # fallback: запуск из исходников
    pyproject = Path(__file__).resolve().parent.parent / 'pyproject.toml'
    try:
        with pyproject.open('rb') as f:
            data = tomllib.load(f)
        return data['project']['version']
    except (OSError, KeyError):
        return 'unknown'


class Container:
    program: str = 'clipik'
    protocol: str = 'CLIPIK'
    version: str = _resolve_version()

    command: str
    session: str | None = None
    hostname: str
    service_name: str
    service_type: str = '_clipik._tcp.local.'
    zeroconf: "Zeroconf" | None

    config: "Config"
    db_connection: sqlite3.Connection
    fresh_config: bool
    fresh_config_path: Path
    config_path: Path
    set_clipboard: SetClipboardFn | None = None
    listen_clipboard: ListenClipboardFn | None = None
    discover_services: DiscoverServicesFn | None = None
    register_service: RegisterServiceFn | None = None
    unregister_service: UnregisterServiceFn | None = None
    required_utils: list[str] = []
    servers: set[ServerConnection] = set()
    interface_ips: list[str] = []

    def __init__(
        self,
        command: str,
        config: "Config",
        db_connection: sqlite3.Connection,
        fresh_config: bool,
        fresh_config_path: Path,
        config_path: Path,
        set_clipboard: SetClipboardFn | None = None,
        listen_clipboard: ListenClipboardFn | None = None,
        discover_services: DiscoverServicesFn | None = None,
        register_service: RegisterServiceFn | None = None,
        unregister_service: UnregisterServiceFn | None = None,
        zeroconf: "Zeroconf" | None = None,
    ):
        self.command = command

        if command == 'client':
            self.session = getpass.getuser()

            if os.name == 'nt' or sys.platform == 'darwin': # Windows / MacOS
                pass
            else: # Linux / Unix
                if sid := os.getenv('XDG_SESSION_ID'):
                    self.session = f"{self.session} - logind-{sid}"
                elif wd := os.getenv('WAYLAND_DISPLAY'):
                    self.session = f"{self.session} - {wd}"
                elif d := os.getenv('DISPLAY'):
                    self.session = f"{self.session} - x11-{d}"
                else:
                    self.session = f"{self.session} - Unknown"

        self.hostname = socket.gethostname()
        self.service_name = f"clipik-{self.hostname}"

        self.config = config
        self.db_connection = db_connection
        self.fresh_config = fresh_config
        self.fresh_config_path = fresh_config_path
        self.config_path = config_path
        self.zeroconf = zeroconf
        self.set_clipboard = set_clipboard
        self.listen_clipboard = listen_clipboard
        self.discover_services = discover_services
        self.register_service = register_service
        self.unregister_service = unregister_service

        if self.config.interfaces:
            self.interface_ips = get_ips_by_interface(self.config.interfaces)
        else:
            self.interface_ips = [get_default_ip()]

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
