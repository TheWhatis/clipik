import asyncio
from loguru import logger
from .websocket import connect_to_server, disconnect_from_server
from .container import Container
from .functions import is_ip_allowed


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


async def start(container: Container):
    try:
        logger.info('Version [{}]', container.version)
        await _discover(container)
    except Exception as e:
        logger.critical('Error setting up and deploy client: [{}]', e)
