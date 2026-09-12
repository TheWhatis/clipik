import os
import asyncio
from collections.abc import Callable, Awaitable, AsyncGenerator
import websockets
from typing import TypeAlias
from websockets.asyncio.server import ServerConnection
from clipik.logger import logger
from clipik.variables import PROTOCOL, PEER_PORT
from clipik.model import (
    ClipboardContent,
    HandshakeEvent,
    HandshakeAckEvent,
    ClipboardEvent,
)


SetClipboardFn: TypeAlias = Callable[[ClipboardContent], Awaitable[None]]
ListenClipboardFn: TypeAlias = Callable[[], AsyncGenerator[ClipboardContent, None]]
IsDuplicateClipboardFn: TypeAlias = Callable[[ClipboardContent], Awaitable[bool]]


_HANDSHAKE_TIMEOUT = os.getenv('CLIPIK_HANDSHAKE_TIMEOUT', default=7)
_HANDSHAKE_TIMEOUT = int(_HANDSHAKE_TIMEOUT)
_CLIENTS: set[ServerConnection] = set()


async def _ws_handler(websocket: ServerConnection, set_clipboard: SetClipboardFn, is_duplicate_clipboard: IsDuplicateClipboardFn):
    try:
        msg = await asyncio.wait_for(websocket.recv(), timeout=_HANDSHAKE_TIMEOUT)

        try:
            event = HandshakeEvent.model_validate_json(msg)
        except Exception as e:
            logger.warning('Invalid handshake [{}]', msg)
            await websocket.close(code=1000, reason='Invalid handshake')
            return

        if event.protocol != PROTOCOL:
            logger.warning('Invalid handshake protocol [{}]', event.protocol)
            await websocket.close(code=1000, reason='Invalid handshake')
            return

        await websocket.send(HandshakeAckEvent().model_dump_json())
    except Exception as e:
        logger.warning('Handshake failed: [{}]', e)

    _CLIENTS.add(websocket)
    peer = websocket.remote_address[0]
    logger.info('Client connected: [{}]', peer)

    set_clipboard_tasks: list[asyncio.Task] = []

    try:
        async for msg in websocket:
            try:
                event = ClipboardEvent.model_validate_json(msg)
                content = ClipboardContent(mime=event.mime, data=event.data)

                logger.debug('Setting clipboard from [{}]: [{}]', peer, content.mime)
                if await is_duplicate_clipboard(content):
                    logger.debug('Clipboard from [{}] is duplicate: [{}]', peer, content.mime)
                    continue

                set_clipboard_tasks.append(asyncio.create_task(set_clipboard(content)))
                logger.debug('Set clipboard from [{}]: [{}]', peer, content.mime)
            except Exception as e:
                logger.error('Error listen peer [{}]: [{}]', peer, e)
    except websockets.exceptions.ConnectionClosed:
        logger.info('Client disconnected: [{}]', peer)
    finally:
        _CLIENTS.remove(websocket)

        for task in set_clipboard_tasks:
            task.cancel()


async def start_websocket_server(
    set_clipboard: SetClipboardFn,
    is_duplicate_clipboard: IsDuplicateClipboardFn
):
    async def handler(websocket: ServerConnection):
        await _ws_handler(websocket, set_clipboard, is_duplicate_clipboard)

    async with websockets.serve(handler, '0.0.0.0', PEER_PORT):
        logger.info('Websocket server started on [{}]', PEER_PORT)
        await asyncio.Future()


async def broadcast_local(listen_clipboard: ListenClipboardFn):
    async for content in listen_clipboard():
        if not content.data:
            continue

        event = ClipboardEvent(
            mime=content.mime,
            data=content.data if isinstance(content.data, str) else content.data,
        )

        payload = event.model_dump_json()

        try:
            if _CLIENTS:
                coros = []
                for client in _CLIENTS:
                    coros.append(client.send(payload))

                await asyncio.gather(*coros, return_exceptions=True)

                logger.debug('Broadcasted to [{}] clients', len(_CLIENTS))
        except Exception as e:
            logger.error(
                'Error [{}] broadcasting to [{}] clients, mime [{}]',
                e,
                len(_CLIENTS),
                content.mime
            )


async def connect_to_server(host: str, port: int, set_clipboard: SetClipboardFn, is_duplicate_clipboard: IsDuplicateClipboardFn):
    url = f"ws://{host}:{port}"

    try:
        async with websockets.connect(url) as ws:
            await ws.send(HandshakeEvent().model_dump_json())

            msg = await asyncio.wait_for(ws.recv(), timeout=_HANDSHAKE_TIMEOUT)
            ack = HandshakeAckEvent.model_validate_json(msg)

            if ack.protocol != PROTOCOL:
                logger.warning('Invalid protocol [{}] for [{}]', ack.protocol, host)
                return

            logger.info('Connected to server [{}]', url)

            async for msg in ws:
                try:
                    event = ClipboardEvent.model_validate_json(msg)

                    content = ClipboardContent(
                        mime=event.mime,
                        data=event.data,
                    )

                    logger.debug('Setting clipboard from server [{}], mime [{}]', url, event.mime)
                    if await is_duplicate_clipboard(content):
                        logger.debug(
                            'Clipboard from server [{}] is duplicate, mime [{}]',
                            url,
                            event.mime
                        )

                        continue

                    await set_clipboard(content)
                    logger.debug('Set clipboard from server [{}], mime [{}]', url, event.mime)
                except Exception as e:
                    logger.error('Error from server [{}]: [{}]', url, e)
    except Exception as e:
        logger.warning('Failed to connect [{}]. Error: [{}]', url, e)
