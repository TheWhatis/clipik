import asyncio
from clipik.utils import get_skipped_required_utils
from clipik.zeroconf import register_service, unregister_service, discover_services
from clipik.variables import GRAPHIC_PROTOCOL
from clipik.logger import logger
from clipik.websocket import broadcast_local, connect_to_server, start_websocket_server
from clipik.model import NewServiceEvent, LoseServiceEvent


if GRAPHIC_PROTOCOL == 'x11':
    from clipik.clipboard.x11 import set_clipboard, listen_clipboard, is_duplicate_clipboard
else:
    from clipik.clipboard.wayland import set_clipboard, listen_clipboard, is_duplicate_clipboard


_SERVER_TASKS: dict[str, asyncio.Task] = {}


async def _discover():
    async for event in discover_services():
        if event.event == 'new_service':
            _SERVER_TASKS[event.name] = asyncio.create_task(
                connect_to_server(
                    host=event.host,
                    port=event.port,
                    set_clipboard=set_clipboard,
                    is_duplicate_clipboard=is_duplicate_clipboard
                )
            )
            continue

        if event.event == 'lose_service' and event.name in _SERVER_TASKS:
            task = _SERVER_TASKS[event.name]
            del _SERVER_TASKS[event.name]
            task.cancel()


async def _main():
    await asyncio.gather(
        start_websocket_server(set_clipboard, is_duplicate_clipboard),
        broadcast_local(listen_clipboard),
        _discover(),
    )


def main():
    skipped_utils: list[str] = get_skipped_required_utils()

    if skipped_utils:
        skipped_utils_str: str = ', '.join(skipped_utils)
        raise InitializationError(f'Utils [{skipped_utils_str}] is required, install it')

    try:
        register_service()
        asyncio.run(_main())
    except Exception as e:
        logger.critical('Error while asyncio.run: [{}]', e)
        raise e
    finally:
        unregister_service()
