import asyncio
from zeroconf import Zeroconf
from clipik.utils import get_skipped_required_utils
from clipik.zeroconf import register_service, unregister_service, discover_services, get_zeroconf
from clipik.variables import GRAPHIC_PROTOCOL
from clipik.logger import logger
from clipik.websocket import broadcast_local, connect_to_server, start_websocket_server
from clipik.model import NewServiceEvent, LoseServiceEvent
from clipik.exception import InitializationError


if GRAPHIC_PROTOCOL == 'x11':
    from clipik.clipboard.x11 import set_clipboard, listen_clipboard, is_duplicate_clipboard
else:
    from clipik.clipboard.wayland import set_clipboard, listen_clipboard, is_duplicate_clipboard


_SERVER_TASKS: dict[str, asyncio.Task] = {}


async def _discover(zc: Zeroconf):
    async for event in discover_services(zc):
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


async def _main(zc: Zeroconf):
    ws_task = asyncio.create_task(
        start_websocket_server(
            set_clipboard,
            is_duplicate_clipboard
        )
    )

    await asyncio.sleep(0.1)
    register_service(zc)

    try:
        await asyncio.gather(
            ws_task,
            broadcast_local(listen_clipboard),
            _discover(zc),
        )
    finally:
        unregister_service(zc)


def main():
    skipped_utils: list[str] = get_skipped_required_utils()

    if skipped_utils:
        skipped_utils_str: str = ', '.join(skipped_utils)
        raise InitializationError(f'Utils [{skipped_utils_str}] is required, install it')

    zc = get_zeroconf()

    try:
        asyncio.run(_main(zc))
    except KeyboardInterrupt:
        logger.info('Bye-bye!!')
    except Exception as e:
        logger.critical('Error while asyncio.run: [{}]', e)
        raise e
