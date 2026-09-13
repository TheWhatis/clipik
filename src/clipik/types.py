from collections.abc import Callable, Awaitable, AsyncGenerator
from typing import TYPE_CHECKING, TypeAlias


if TYPE_CHECKING:
    from clipik.model import ClipboardContent


SetClipboardFn: TypeAlias = Callable[["ClipboardContent"], Awaitable[None]]
ListenClipboardFn: TypeAlias = Callable[[int], AsyncGenerator["ClipboardContent", None]]
IsDuplicateClipboardFn: TypeAlias = Callable[["ClipboardContent"], Awaitable[bool]]
