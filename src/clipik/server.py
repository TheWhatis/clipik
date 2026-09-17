import asyncio
from loguru import logger
from .websocket import start_websocket_server
from .container import Container


async def start(container: Container):
    try:
        logger.info('Version [{}]', container.version)
        ready = asyncio.Event()
        ws_task = asyncio.create_task(start_websocket_server(container, ready))

        await ready.wait()
        container.register_service(container)

        try:
            await ws_task
        finally:
            container.unregister_service(container)
    except Exception as e:
        logger.critical('Error setting up and deploy server: [{}]', e)
