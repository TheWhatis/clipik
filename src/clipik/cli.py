import os
import sys
import signal
import asyncio
import argparse
from loguru import logger
from pathlib import Path
from .container import Container
from .config import write_fresh_config, read_config_file
from .server import start as server_start
from .client import start as client_start
from .database import initialize_database, close_database
from .functions import list_contents, first_contents, last_contents, paste_clipboard
from .model import ServerConfig, ClientConfig, Config
from .logger import initialize_logger


def _add_default_options(parser: argparse.ArgumentParser):
    parser.add_argument(
        '--version',
        action='version',
        version=f"{Container.program} {Container.version}"
    )

    parser.add_argument(
        '--config',
        dest='config',
        type=Path,
        default=None,
        metavar='PATH',
        help='Force choice config file',
    )

    parser.add_argument(
        '--log-level',
        dest='log_level',
        type=str,
        default=None,
        metavar='LEVEL',
        help='Logging level, default [INFO]'
    )

    parser.add_argument(
        '--log-dir',
        dest='log_dir',
        type=Path,
        default=None,
        metavar='PATH',
        help='Force choice log directory',
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
        '--database',
        dest='database',
        type=Path,
        default=None,
        metavar='PATH',
        help='Force choice database file'
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Container.program,
        description='Synchronize clipboard by network',
    )

    _add_default_options(parser)

    subparsers = parser.add_subparsers(
        title='command',
        dest='command',
        metavar='COMMAND'
    )
    server = subparsers.add_parser('server', help='Run synchronization server')

    _add_default_options(server)

    server.add_argument(
        '--port',
        type=int,
        default=None,
        metavar='PORT',
        help='WebSocket TCP-port',
    )

    client = subparsers.add_parser('client', help='Run synchronization client')
    _add_default_options(client)

    list_parser = subparsers.add_parser('list', help='Get list clipboard history')
    _add_default_options(list_parser)

    list_parser.add_argument(
        '--format',
        dest='format',
        choices=('raw', 'json'),
        type=str,
        default='raw',
        metavar='FORMAT',
        help='Choice format output [raw]'
    )

    list_parser.add_argument(
        '--limit',
        dest='limit',
        type=int,
        default=15,
        metavar='LIMIT',
        help='Output limit [15]'
    )

    first = subparsers.add_parser('first', help='Get first clipboard element')
    _add_default_options(first)

    first.add_argument(
        '--format',
        dest='format',
        choices=('raw', 'json'),
        type=str,
        default='raw',
        metavar='FORMAT',
        help='Choice format output [raw]',
    )

    last = subparsers.add_parser('last', help='Get last clipboard element')
    _add_default_options(last)

    last.add_argument(
        '--format',
        dest='format',
        choices=('raw', 'json'),
        type=str,
        default='raw',
        metavar='FORMAT',
        help='Choice format output [raw]',
    )

    paste = subparsers.add_parser('paste', help='Paste record in clipboard')
    _add_default_options(paste)
    paste.add_argument('id')

    return parser


def _initialize_loop(container: Container):
    initialize_logger(container.config)

    if container.fresh_config:
        logger.info('Config has been freshed [{}]', container.fresh_config_path)

    logger.info('Initialized config')
    for key, value in container.config.model_dump().items():
        logger.info('Config [{}]=[{}]', key, value)



def _main_server(container: Container):
    _initialize_loop(container)

    if sys.platform == 'android': # Android
        logger.error('Android [{}] does not supports', sys.platform)
    else:
        from .mdns.zeroconf import register_service, unregister_service, get_zeroconf

        logger.info('Add register_service to Container')
        container.register_service = register_service

        logger.info('Add unregister_service to Container')
        container.unregister_service = unregister_service

        logger.info('Add zeroconf to Container')
        container.zeroconf = get_zeroconf(container.config.interfaces)

    try:
        logger.info('Start [server_start] in asyncio.run')
        asyncio.run(server_start(container))
    except KeyboardInterrupt:
        logger.info('Bye-Bye!!!')
        sys.exit(130)
    except Exception as e:
        logger.critical('Error while running server [{}]', e)
        sys.exit(1)


def _main_client(container: Container):
    _initialize_loop(container)

    logger.info('Set listen_clipboard to Container')

    if os.name == 'nt': # Windows
        logger.error('Windows [{}] does not supports', os.name)
        return
    elif sys.platform == 'darwin': # macOS
        logger.error('MacOS [{}] does not supports', sys.platform)
        return
    elif os.getenv('WAYLAND_DISPLAY', default=None):
        from .clipboard.linux import listen_clipboard_wayland
        container.listen_clipboard = listen_clipboard_wayland
    else:
        from .clipboard.linux import listen_clipboard_x11
        container.listen_clipboard = listen_clipboard_x11

    if sys.platform == 'android': # Android
        logger.error('Android [{}] does not supports', sys.platform)
    else:
        from .mdns.zeroconf import discover_services, get_zeroconf

        logger.info('Add discover_services to Container')
        container.discover_services = discover_services

        logger.info('Add zeroconf to Container')
        container.zeroconf = get_zeroconf(container.config.interfaces)

    try:
        logger.info('Start [client_start] in asyncio.run')
        asyncio.run(client_start(container))
    except KeyboardInterrupt:
        logger.info('Bye-Bye!!!')
        sys.exit(130)
    except Exception as e:
        logger.critical('Error while running client [{}]', e)
        sys.exit(1)


def _main_paste(container: Container, args: argparse.ArgumentParser):
    if os.name == 'nt': # Windows
        print(f"Windows [{os.uname}] does not supports")
        return
    elif sys.platform == 'darwin': # macOS
        print(f"MacOS [{os.uname}] does not supports")
        return
    elif os.getenv('WAYLAND_DISPLAY', default=None):
        from .clipboard.linux import set_clipboard_wayland
        container.set_clipboard = set_clipboard_wayland
    else:
        from .clipboard.linux import set_clipboard_x11
        container.set_clipboard = set_clipboard_x11

    try:
        asyncio.run(paste_clipboard(container, args))
    except KeyboardInterrupt:
        print("Bye-bye!!!", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        raise e
        print(f"Error while paste clipboard [{e}]")
        sys.exit(1)


def main():
    parser = _build_parser()
    args = parser.parse_args()

    def _shutdown_handler(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    if os.name == 'nt':
        config_path = Path(os.getenv('APPDATA', '~')) / 'clipik'
    elif sys.platform == 'darwin': # MacOS
        config_path = Path('~/Library/Application Support/Clipik').expanduser()
    else:
        config_path = Path('~/.config/clipik').expanduser()

    if args.command == 'server':
        config = ServerConfig
        config_path = config_path / 'server.json'
    else:
        config = ClientConfig
        config_path = config_path / 'client.json'

    fresh_config_path = config_path
    fresh_config: Config = write_fresh_config(fresh_config_path, config)

    overrides = {
        key: value
        for key, value in vars(args).items()
        if value is not None
    }

    config_path: Path = overrides.get('config', config_path)
    config: Config = read_config_file(config_path, config, overrides)

    do_log = args.command in ['server', 'client']
    db_connection = initialize_database(
        config,
        args.command != 'server',
        do_log,
    )

    try:
        try:
            container = Container(
                command=args.command,
                config=config,
                db_connection=db_connection,
                fresh_config=fresh_config,
                fresh_config_path=fresh_config_path,
                config_path=config_path,
            )
        except Exception as e:
            initialize_logger(config)
            logger.critical('Error [{}] container initialization', e)
            return

        if args.command == 'server':
            _main_server(container)
            return

        if args.command == 'client':
            _main_client(container)
            return

        if args.command == 'list':
            list_contents(container, args)
            return

        if args.command == 'first':
            first_contents(container, args)
            return

        if args.command == 'last':
            last_contents(container, args)
            return

        if args.command == 'paste':
            _main_paste(container, args)
            return

        parser.error('Command not passed, write [server, client, list, first, last or paste], for details use --help')
    finally:
        close_database(db_connection, do_log)
