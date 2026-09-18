import asyncio
import signal
from loguru import logger
from .websocket import start_websocket_server
from .container import Container


async def start(container: Container):
    try:
        logger.info('Version [{}]', container.version)
        ready = asyncio.Event()
        ws_task = asyncio.create_task(start_websocket_server(container, ready))

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        await ready.wait()
        container.register_service(container)

        try:
            # ждём либо завершения WS, либо сигнала
            done, pending = await asyncio.wait(
                [ws_task, asyncio.create_task(stop.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        finally:
            container.unregister_service(container)
    except Exception as e:
        logger.critical('Error setting up and deploy server: [{}]', e)
