import json
from pathlib import Path
from clipik.model import Config


def write_fresh_config(path: Path) -> bool:
    """Создает файл конфига с нуля, если его нет."""
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)

    config = Config()
    config.resolve_properties()
    payload = config.model_dump(
        mode='json',
        include=set([
            'port',
            'size_limit',
            'log_level',
            'handshake_timeout',
        ]),
    )

    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return True


def read_config_file(
    path: Path,
    overrides: dict | None = None,
) -> Config:
    raw = path.read_text(encoding='utf-8')
    config = Config.model_validate_json(raw)

    merged: dict = config.model_dump()

    if overrides:
        known = set(Config.model_fields)
        for key, value in overrides.items():
            if key in known and value is not None:
                merged[key] = value

    config = Config(**merged)
    config.resolve_properties()
    return config
