from collections.abc import Callable, Awaitable, AsyncGenerator
from typing import TYPE_CHECKING, TypeAlias


if TYPE_CHECKING:
    from .model import ClipboardContent, NewServiceEvent, LoseServiceEvent
    from .container import Container


SetClipboardFn: TypeAlias = Callable[["ClipboardContent"], Awaitable[bool]]
ListenClipboardFn: TypeAlias = Callable[[int], AsyncGenerator["ClipboardContent", None]]
DiscoverServicesFn: TypeAlias = Callable[["Container"], AsyncGenerator["NewServiceEvent | LoseServiceEvent", None]]
RegisterServiceFn: TypeAlias = Callable[["Container"], None]
UnregisterServiceFn: TypeAlias = Callable[["Container"], None]
