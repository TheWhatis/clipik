import os
from enum import Enum


class GraphicProtocol(Enum):
    X11 = 'x11'
    WAYLAND = 'wayland'

    @classmethod
    def detect(cls) -> 'GraphicProtocol':
        """Автоопределение по WAYLAND_DISPLAY."""
        return cls.WAYLAND if os.getenv('WAYLAND_DISPLAY') else cls.X11
