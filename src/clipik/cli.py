import os
import sys
import asyncio
import argparse
from loguru import logger
from pathlib import Path
from clipik.exception import InitializationError
from clipik.zeroconf import register_service, unregister_service, discover_services, get_zeroconf
from clipik.websocket import broadcast_local, connect_to_server, start_websocket_server
from clipik.config import write_fresh_config, read_config_file
from clipik.logger import initialize_logger
from clipik.container import Container


_SERVER_TASKS: dict[str, asyncio.Task] = {}
_AWAITING_TASKS: list[asyncio.Task] = []


async def _await_task(task: asyncio.Task):
    await task


async def _discover(container: Container):
    async for event in discover_services(container):
        if event.event == 'new_service':
            if not container.config.is_ip_allowed(event.ip):
                logger.warning('Ip [{}] is not allowed, stop connecting to service', event.ip)
            else:
                _SERVER_TASKS[event.name] = asyncio.create_task(
                    connect_to_server(
                        host=event.host,
                        port=event.port,
                        container=container,
                    )
                )

            continue

        if event.event == 'lose_service' and event.name in _SERVER_TASKS:
            task = _SERVER_TASKS[event.name]
            task.cancel()
            _AWAITING_TASKS.append(asyncio.create_task(_await_task(task)))
            del _SERVER_TASKS[event.name]


async def _main(container: Container):
    ws_task = asyncio.create_task(start_websocket_server(container))

    await asyncio.sleep(0.1)
    register_service(container)

    try:
        await asyncio.gather(
            ws_task,
            broadcast_local(container),
            _discover(container),
        )
    finally:
        unregister_service(container)

        for _, task in _SERVER_TASKS.items():
            task.cancel()
            _AWAITING_TASKS.append(task)

        await asyncio.gather(*_AWAITING_TASKS, return_exceptions=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Container.program,
        description='Synchronize clipboard by network',
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f"{Container.program} {Container.version}"
    )

    parser.add_argument(
        '--config',
        dest='config',
        type=Path,
        default=Path.home() / '.config' / 'clipik' / 'config.json',
        metavar='PATH',
        help='Force choice config file',
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        metavar='PORT',
        help='WebSocket TCP-port',
    )

    parser.add_argument(
        '--size-limit',
        dest='size_limit',
        type=int,
        default=None,
        metavar='BYTES',
        help='Max size WS-messages and stdout from wayland/x11 clipboard'
    )

    parser.add_argument(
        '--handshake-timeout',
        dest='handshake_timeout',
        type=int,
        default=None,
        metavar='SECONDS',
        help='Timeout for wait to websocket handshake',
    )

    parser.add_argument(
        '--log-level',
        dest='log_level',
        type=str,
        default=None,
        metavar='LEVEL',
        help='Logging level, default [INFO]'
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def parse_overrides(argv: list[str] | None = None) -> dict[str, object]:
    args = parse_args(argv)

    return {
        key: value
        for key, value in vars(args).items()
        if value is not None
    }


def main():
    fresh_config_path = Path.home() / '.config' / 'clipik' / 'config.json'
    fresh_config = write_fresh_config(fresh_config_path)
    overrides = parse_overrides()
    config_path: Path = overrides.get('config')
    config = read_config_file(config_path, overrides)
    config.resolve_properties()
    initialize_logger(config)

    if fresh_config:
        logger.info('Config has been freshed [{}]', fresh_config_path)

    logger.info('Config file [{}]', config_path)

    logger.info('Initialized config')
    for key, value in config.model_dump().items():
        logger.info('Config [{}]=[{}]', key, value)

    if os.name == 'nt': # Windows
        logger.error('Windows [{}] does not supports', os.name)
        return
    elif sys.platform == 'darwin': # macOS
        logger.error('MacOS [{}] does not supports', sys.platform)
        return
    else: # Linux / Unix
        from clipik.clipboard.linux import set_clipboard, listen_clipboard

    logger.info('Initialize container')

    try:
        container = Container(
            config=config,
            zeroconf=get_zeroconf(),
            set_clipboard=set_clipboard,
            listen_clipboard=listen_clipboard,
        )
    except Exception as e:
        logger.critical('Error [{}] container initialization', e)
        return

    try:
        logger.info('Version [{}]', container.version)
        logger.info('Runnine asyncio main entrypoint [_main]')
        asyncio.run(_main(container))
    except KeyboardInterrupt:
        logger.info('Bye-bye!!')
    except Exception as e:
        logger.critical('Error while asyncio.run: [{}]', e)
        raise e
