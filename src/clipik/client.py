import asyncio
from loguru import logger
from .websocket import connect_to_server, disconnect_from_server
from .container import Container
from .functions import is_ip_allowed
from .model import ClipboardEvent, event_to_bytes


async def _discover(container: Container):
    tasks: list[asyncio.Task] = []

    try:
        async for event in container.discover_services(container):
            if event.event == 'new_service':
                if not is_ip_allowed(container.config, event.ip):
                    logger.warning('Ip [{}] is not allowed, stop connecting to service', event.ip)
                else:
                    tasks.append(asyncio.create_task(connect_to_server(
                        host=event.host,
                        port=event.port,
                        container=container,
                    )))
            elif event.event == 'lose_service':
                tasks.append(asyncio.create_task(disconnect_from_server(
                    host=event.host,
                    container=container,
                )))
            else:
                logger.warning('Undefined disconver event [{}]', event)
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks)


async def _listen_clipboard_and_broadcasting(container: Container):
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



async def start(container: Container):
    try:
        logger.info('Version [{}]', container.version)

        await asyncio.gather(
            _discover(container),
            _listen_clipboard_and_broadcasting(container),
        )
    except Exception as e:
        logger.critical('Error setting up and deploy client: [{}]', e)
