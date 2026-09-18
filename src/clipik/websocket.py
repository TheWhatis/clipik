import asyncio
import websockets
from loguru import logger
from websockets.asyncio.server import ServerConnection
from .container import Container
from .model import (
    Clipboard,
    HandshakeEvent,
    HandshakeAckEvent,
    ClipboardEvent,
    event_to_bytes,
    event_from_bytes,
)
from .database import add_to_history
from .functions import is_ip_allowed, supports_versions


async def _add_to_history(connection, clipboard):
    i = 0
    while True:
        i += 1

        try:
            await asyncio.to_thread(add_to_history, connection, clipboard)
            break
        except Exception:
            await asyncio.sleep(i)


async def _ws_handler(
    websocket: ServerConnection,
    container: Container,
):
    try:
        ip = websocket.remote_address[0]

        if not is_ip_allowed(container.config, ip):
            logger.warning('Client ip [{}] is not allowed', ip)
            await websocket.close(code=1008, reason='Ip is not allowed')
            return
    except Exception as e:
        logger.warning('Error with check client ip [{}]', e)
        return

    peer = websocket.remote_address[0]

    try:
        try:
            msg = await asyncio.wait_for(
                websocket.recv(),
                timeout=container.config.handshake_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning('Handshake timeout from [{}]', peer)
            await websocket.close(code=1002, reason='Handshake timeout')
            return

        try:
            event: HandshakeEvent = event_from_bytes(msg)
        except Exception as e:
            logger.warning('Invalid handshake [{}]', msg)
            await websocket.close(code=1007, reason='Invalid handshake')
            return

        if event.event != 'handshake':
            logger.warning('Invalid handshake event [{}]', event)
            await websocket.close(code=1007, reason='Invalid handshake')
            return

        if event.protocol != container.protocol:
            logger.warning('Invalid handshake protocol [{}]', event.protocol)
            await websocket.close(code=1007, reason='Invalid protocol')
            return

        if not supports_versions(event.version, container.version):
            logger.warning(
                'Version does not supports [{}], current [{}]',
                event.version,
                container.version
            )

            await websocket.close(code=1002, reason=f"Version must be more or equal {container.version}")
            return

        ack_event = HandshakeAckEvent(
            protocol=container.protocol,
            version=container.version,
        )

        await websocket.send(event_to_bytes(ack_event))
    except Exception as e:
        logger.warning('Handshake failed: [{}]', e)
        return

    logger.info('Client connected: [{}]', peer)
    tasks: list[asyncio.Task] = []

    try:
        async for msg in websocket:
            try:
                event: ClipboardEvent = event_from_bytes(msg)

                if event.event != 'clipboard':
                    logger.warning('Invalid clipboard [{}] from [{}]', event, peer)
                    await websocket.close(code=1007, reason='Invalid clipboard')
                    return

                hostname = event.hostname

                if hostname == container.hostname:
                    hostname = 'localhost'

                clipboard = Clipboard(
                    mime=event.mime,
                    data=event.data,
                    hostname=f"[{hostname}] [{event.session}]",
                    ip=peer,
                )

                logger.debug('Save clipboard to history from [{}:{}]: [{}]', hostname, clipboard.ip, clipboard.mime)

                tasks.append(
                    asyncio.create_task(_add_to_history(
                        container.db_connection,
                        clipboard
                    ))
                )
            except Exception as e:
                logger.error('Error listen peer [{}]: [{}]', peer, e)
    except websockets.exceptions.ConnectionClosed:
        logger.info('Client disconnected: [{}]', peer)
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)


async def start_websocket_server(container: Container, ready: asyncio.Event | None = None):
    async def handler(websocket: ServerConnection):
        await _ws_handler(websocket, container)

    async with websockets.serve(
        handler,
        '0.0.0.0',
        container.config.port,
        max_size=container.config.size_limit
    ):
        logger.info('Websocket server started on [{}]', container.config.port)
        ready.set()
        await asyncio.Future()


async def _broadcast_local(container: Container):
    tasks: list[asyncio.Task] = []

    try:
        async for content in container.listen_clipboard(container.config.size_limit):
            if not content.data:
                continue

            event = ClipboardEvent(
                mime=content.mime,
                data=content.data,
                hostname=container.hostname,
                session=container.session,
            )

            payload = event_to_bytes(event)

            try:
                if container.servers:
                    logger.debug('Broadcasting to [{}] servers', len(container.servers))

                    for server in container.servers:
                        tasks.append(asyncio.create_task(server.send(payload)))
            except Exception as e:
                logger.error(
                    'Error [{}] broadcasting to [{}] servers, mime [{}]',
                    e,
                    len(container.servers),
                    content.mime
                )
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)


async def _listen_server_messages(ws: ServerConnection):
    ip = ws.remote_address[0]

    async for msg in ws:
        try:
            event = event_from_bytes(msg)
            logger.info('Received event [{}] from server [{}]', event, ip)
        except Exception as e:
            logger.warning('Error [{}] receiving from [{}]', e, ip)


async def connect_to_server(
    host: str,
    port: int,
    container: Container,
):
    url = f"ws://{host}:{port}"

    logger.info('Trying connecting to server [{}]', url)

    try:
        async with websockets.connect(url, max_size=container.config.size_limit) as server:
            container.servers.add(server)

            try:
                event = HandshakeEvent(
                    protocol=container.protocol,
                    version=container.version,
                )

                await server.send(event_to_bytes(event))

                msg = await asyncio.wait_for(
                    server.recv(),
                    timeout=container.config.handshake_timeout
                )

                try:
                    ack: HandshakeAckEvent = event_from_bytes(msg)
                except Exception as e:
                    logger.warning('Invalid ack [{}]', msg)
                    await server.close(code=1007, reason='Invalid handshake')
                    return

                if ack.event != 'handshake_ack':
                    logger.warning('Invalid ack event [{}]', ack)
                    await server.close(code=1007, reason='Invalid ack')
                    return

                if ack.protocol != container.protocol:
                    logger.warning('Invalid ack protocol [{}] for [{}]', ack.protocol, host)
                    await server.close(code=1007, reason='Invalid protocol')
                    return

                if not supports_versions(ack.version, container.version):
                    logger.warning(
                        'Version does not supports [{}], current [{}]',
                        ack.version,
                        container.version
                    )

                    await server.close(code=1002, reason=f"Version must be more or equal {container.version}")
                    return

                logger.info('Connected to server [{}]', url)

                await asyncio.gather(
                    _listen_server_messages(server),
                    _broadcast_local(container),
                    return_exceptions=True,
                )
            finally:
                container.servers.remove(server)
    except Exception as e:
        logger.error('Failed to connect [{}]. Error: [{}]', url, e)


async def disconnect_from_server(host: str, container: Container):
    for server in container.servers:
        ip = server.remote_address[0]

        if ip != host:
            continue

        try:
            logger.info('Disconnecting from server [{}]', ip)
            container.servers.remove(server)
            await server.close()
        except Exception as e:
            logger.error('Error disconnecting from server [{}]', ip)
