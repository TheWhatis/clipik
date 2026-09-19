import sys
import gzip
import shutil
import datetime
from pathlib import Path
from loguru import logger
from .config import Config


class _Rotator:
    """Ротация по размеру ИЛИ по времени. Что сработает раньше - то и ротирует."""

    def __init__(self, *, size: int, at: datetime.time):
        self._size_limit = size
        now = datetime.datetime.now()
        self._time_limit = now.replace(
            hour=at.hour, minute=at.minute, second=at.second, microsecond=0
        )
        # Если сейчас уже позже целевого времени - цель на завтра,
        # чтобы не ротировать сразу же при старте.
        if now >= self._time_limit:
            self._time_limit += datetime.timedelta(days=1)

    def should_rotate(self, message, file) -> bool:
        # Условие 1: размер
        file.seek(0, 2)

        if file.tell() + len(message) > self._size_limit:
            return True

        # Условие 2: время
        excess = message.record['time'].timestamp() - self._time_limit.timestamp()
        if excess >= 0:
            elapsed_days = datetime.timedelta(seconds=excess).days
            self._time_limit += datetime.timedelta(days=elapsed_days + 1)
            return True

        return False


def _compress_all_logs_except_active(log_dir: Path, active_name: str) -> None:
    """Сжимает ВСЕ .log в директории, кроме активного файла."""
    for log_file in sorted(log_dir.glob('*.log')):
        if log_file.name == active_name:
            continue

        gz_path = log_file.with_suffix('.log.gz')

        # Если .gz уже есть - исходник удаляем, он лишний
        if gz_path.exists():
            log_file.unlink()
            continue

        try:
            with open(log_file, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            log_file.unlink()
        except Exception as e:
            # Не валим сервер из-за одного битого файла
            logger.error('Failed to compress [{}]: [{}]', log_file, e)


def initialize_logger(config: Config) -> None:
    global logger
    config.log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().strftime('%Y-%m-%d')
    active_name = f"{today}.log"

    # Сначала сжимаем всё старое, потом открываем логгер.
    # Порядок важен: если делать наоборот, Loguru займёт активный
    # файл, и он попадёт в сжатие.
    _compress_all_logs_except_active(config.log_dir, active_name)

    logger.remove()

    filepath = str(config.log_dir / '{time:YYYY-MM-DD}.log')
    rotator = _Rotator(size=10 * 1024 * 1024, at=datetime.time(0, 0, 0))

    logger.add(
        filepath,
        level=config.log_level,
        encoding='utf-8',
        rotation=rotator.should_rotate,
        compression='gz'
    )

    logger.add(
        sys.stdout,
        level=config.log_level,
        colorize=True
    )

    logger.add(
        sys.stderr,
        level='ERROR',
        colorize=True,
    )

    logger.info('Log level: [{}]',config.log_level)
    logger.info('Log file is [{}]', filepath)
