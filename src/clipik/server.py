import asyncio
import signal
from loguru import logger
from .websocket import start_websocket_server
from .container import Container
from .database import trim_history


async def _trim_history_each_seven_seconds(container: Container, interval: float = 7.0):
    """Периодически обрезает историю до 1000 записей."""
    while True:
        try:
            logger.debug('Start trim_history with limit [1000] and interval [{}]', interval)
            await asyncio.sleep(interval)

            removed = await trim_history(container.db_connection, 1000)

            if removed:
                logger.info('History trimmed: {} records removed', removed)
        except asyncio.CancelledError:
            # Корректная остановка по cancel()
            raise
        except Exception as e:
            # Одна ошибка БД не должна убивать таску
            logger.error('Error while trimming history: [{}]', e)


async def start(container: Container):
    try:
        logger.info('Version [{}]', container.version)
        ready = asyncio.Event()
        ws_task = asyncio.create_task(start_websocket_server(container, ready))

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: stop.set())

        await trim_history(container.db_connection)

        trim_task = asyncio.create_task(_trim_history_each_seven_seconds(container))

        await ready.wait()
        container.register_service(container)

        try:
            # ждём либо завершения WS, либо сигнала
            done, pending = await asyncio.wait(
                [ws_task, asyncio.create_task(stop.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
        finally:
            trim_task.cancel()
            ws_task.cancel()

            try:
                await trim_task
            except asyncio.CancelledError:
                pass

            try:
                await ws_task
            except asyncio.CancelledError:
                pass

            container.unregister_service(container)
    except Exception as e:
        logger.critical('Error setting up and deploy server: [{}]', e)
        raise e
