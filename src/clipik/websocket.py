import asyncio
import websockets
from loguru import logger
from websockets.asyncio.server import ServerConnection
from clipik.container import Container
from clipik.model import (
    ClipboardContent,
    HandshakeEvent,
    HandshakeAckEvent,
    ClipboardEvent,
    event_to_bytes,
    event_from_bytes,
)


async def _ws_handler(
    websocket: ServerConnection,
    container: Container,
):
    try:
        ip = websocket.remote_address[0]

        if not container.config.is_ip_allowed(ip):
            logger.warning('Client ip [{}] is not allowed', ip)
            await websocket.close(code=1008, reason='Ip is not allowed')
            return
    except Exception as e:
        logger.warning('Error with check client ip [{}]', e)
        return

    try:
        try:
            msg = await asyncio.wait_for(
                websocket.recv(),
                timeout=container.config.handshake_timeout
            )
        except asyncio.TimeoutError:
            logger.warning('Handshake timeout from [{}]', websocket.remote_address[0])
            await websocket.close(code=1002, reason='Handshake timeout')
            return

        try:
            event = event_from_bytes(msg)
        except Exception as e:
            logger.warning('Invalid handshake [{}]', msg)
            await websocket.close(code=1007, reason='Invalid handshake')
            return

        if event.protocol != container.protocol:
            logger.warning('Invalid handshake protocol [{}]', event.protocol)
            await websocket.close(code=1002, reason='Invalid handshake')
            return

        ack_event = HandshakeAckEvent(
            protocol=container.protocol,
            version=container.version,
        )

        await websocket.send(event_to_bytes(ack_event))
    except Exception as e:
        logger.warning('Handshake failed: [{}]', e)
        return

    container.clients.add(websocket)
    peer = websocket.remote_address[0]
    logger.info('Client connected: [{}]', peer)

    set_clipboard_tasks: list[asyncio.Task] = []

    try:
        async for msg in websocket:
            try:
                event = event_from_bytes(msg)
                content = ClipboardContent(mime=event.mime, data=event.data)

                logger.debug('Setting clipboard from [{}]: [{}]', peer, content.mime)
                set_clipboard_tasks.append(asyncio.create_task(container.set_clipboard(content)))
                logger.debug('Set clipboard from [{}]: [{}]', peer, content.mime)
            except Exception as e:
                logger.error('Error listen peer [{}]: [{}]', peer, e)
    except websockets.exceptions.ConnectionClosed:
        logger.info('Client disconnected: [{}]', peer)
    finally:
        container.clients.remove(websocket)

        for task in set_clipboard_tasks:
            task.cancel()

        await asyncio.gather(*set_clipboard_tasks)


async def start_websocket_server(container: Container):
    async def handler(websocket: ServerConnection):
        await _ws_handler(websocket, container)

    async with websockets.serve(
        handler,
        '0.0.0.0',
        container.config.port,
        max_size=container.config.size_limit
    ):
        logger.info('Websocket server started on [{}]', container.config.port)
        await asyncio.Future()


async def broadcast_local(container: Container):
    async for content in container.listen_clipboard(container.config.size_limit):
        if not content.data:
            continue

        event = ClipboardEvent(
            mime=content.mime,
            data=content.data,
        )

        payload = event_to_bytes(event)

        try:
            if container.clients:
                coros = []
                for client in container.clients:
                    coros.append(client.send(payload))

                await asyncio.gather(*coros, return_exceptions=True)

                logger.debug('Broadcasted to [{}] clients', len(container.clients))
        except Exception as e:
            logger.error(
                'Error [{}] broadcasting to [{}] clients, mime [{}]',
                e,
                len(container.clients),
                content.mime
            )


async def connect_to_server(
    host: str,
    port: int,
    container: Container,
):
    url = f"ws://{host}:{port}"

    try:
        async with websockets.connect(url, max_size=container.config.size_limit) as ws:
            event = HandshakeEvent(
                protocol=container.protocol,
                version=container.version,
            )

            await ws.send(event_to_bytes(event))

            msg = await asyncio.wait_for(ws.recv(), timeout=container.config.handshake_timeout)
            ack = event_from_bytes(msg)

            if ack.protocol != container.protocol:
                logger.warning('Invalid protocol [{}] for [{}]', ack.protocol, host)
                return

            logger.info('Connected to server [{}]', url)

            async for msg in ws:
                try:
                    event = event_from_bytes(msg)

                    content = ClipboardContent(
                        mime=event.mime,
                        data=event.data,
                    )

                    logger.debug(
                        'Setting clipboard from server [{}], mime [{}]',
                        url,
                        event.mime,
                    )
                    await container.set_clipboard(content)
                    logger.debug(
                        'Setted clipboard from server [{}], mime [{}]',
                        url,
                        event.mime,
                    )
                except Exception as e:
                    logger.error('Error from server [{}]: [{}]', url, e)
    except Exception as e:
        logger.warning('Failed to connect [{}]. Error: [{}]', url, e)
