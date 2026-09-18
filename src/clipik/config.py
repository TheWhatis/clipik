import os
import sys
import json
from pathlib import Path
from .model import Config, ClientConfig


def _build_def_config(config: type[Config]) -> Config:
    handshake_timeout = int(os.getenv('CLIPIK_HANDSHAKE_TIMEOUT', default=7))
    size_limit = int(os.getenv('CLIPIK_SIZE_LIMIT', default=64 * 1024 * 1024))
    log_level = os.getenv('CLIPIK_LOG_LEVEL', default='INFO')

    log_dir = os.getenv('CLIPIK_LOG_DIR', default=None)

    if log_dir: # Env CLIPIK_LOG_DIR
        log_dir = Path(log_dir)
    elif os.name == 'nt': # Windows
        log_dir = Path(os.getenv('APPDATA', '~')) / 'clipik'
    elif sys.platform == 'darwin':
        log_dir = Path('~/Library/Appliction Support/Clipik').expanduser()
    else: # Linux / Unix
        log_dir = Path('~/.local/clipik').expanduser()

    database = os.getenv('CLIPIK_DATABASE', default=None)

    if database:
        database = Path(database)
    elif os.name == 'nt':
        database = Path(os.getenv('APPDATA', '~')) / 'clipik' / 'clipik.db'
    elif sys.platform == 'darwin':
        database = Path('~/Library/Application Support/Clipik/clipik.db').expanduser()
    else:
        database = Path('~/.local/clipik/clipik.db').expanduser()

    if issubclass(config, ClientConfig):
        return config(
            log_dir=log_dir,
            log_level=log_level,
            size_limit=size_limit,
            handshake_timeout=handshake_timeout,
            database=database,
            interfaces=[],
        )

    port = int(os.getenv('CLIPIK_PORT', default=8765))

    return config(
        port=port,
        log_dir=log_dir,
        log_level=log_level,
        size_limit=size_limit,
        handshake_timeout=handshake_timeout,
        database=database,
        allowed_ips=[],
        interfaces=[],
    )


def write_fresh_config(path: Path, config: type[Config]) -> bool:
    """Создает файл конфига с нуля, если его нет."""
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)

    config: Config = _build_def_config(config)
    payload = config.model_dump(
        mode='json',
        include=set([
            'port',
            'size_limit',
            'log_level',
            'handshake_timeout',
            'log_dir',
            'interfaces',
        ]),
    )

    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return True


def read_config_file(
    path: Path,
    config: type[Config],
    overrides: dict[str, object] = {},
) -> Config:
    if not path.exists():
        write_fresh_config(path, config)

    raw = path.read_text(encoding='utf-8')

    def_config = _build_def_config(config)
    merged = {**json.loads(raw), **(overrides if overrides else {})}

    for key in config.model_fields:
        if key in merged and merged[key]:
            continue

        merged[key] = getattr(def_config, key)

    return config(**merged)
