import sqlite3
import hashlib
import asyncio
from loguru import logger
from .model import Clipboard, Config
from .exception import InitializationError

_WRITE_DATABASE_LOCK = asyncio.Lock()


def initialize_database(
        config: Config,
        immutable: bool,
        do_log: bool
) -> sqlite3.Connection:
    if immutable:
        if do_log:
            logger.warning(
                'Reading database in immutable (readonly): [{}]',
                config.database
            )

        if not config.database.exists():
            raise InitializationError(
                f"Error while read immutable database [{config.database}]"
            )

    config.database.parent.mkdir(parents=True, exist_ok=True)

    connection: sqlite3.Connection = sqlite3.connect(
        f"file:{config.database}?immutable=1" if immutable else config.database,
        check_same_thread=False,
        uri=immutable,
    )

    connection.row_factory = sqlite3.Row

    if not immutable:
        connection.execute("PRAGMA journal_mode = WAL")   # читатели не блокируют писателя
        connection.execute("PRAGMA synchronous = NORMAL") # быстрее, безопасно в WAL
        connection.execute("PRAGMA busy_timeout = 5000")  # ждать 5с при блокировке
        connection.execute("PRAGMA foreign_keys = ON")    # если нужны F

        connection.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            mime       TEXT NOT NULL,
            data       BLOB NOT NULL,
            data_hash  BLOB NOT NULL,
            hostname   TEXT NOT NULL,
            ip         TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_history_created_at ON history (created_at DESC)'
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_history_hostname ON history (hostname)'
        )
        connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_history_data_hash ON history (data_hash);'
        )

    return connection


def close_database(connection: sqlite3.Connection | None, do_log: bool) -> None:
    if connection is None:
        return

    try:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except sqlite3.OperationalError as e:
        if do_log:
            logger.warning('Checkpoint failed [{}]', e)

    try:
        if do_log:
            logger.info('Close database')

        connection.close()
    except Exception as e:
        logger.critical('Close failed [{}]', e)


def _data_hash(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _add_to_history(connection: sqlite3.Connection, content: Clipboard) -> int:
    try:
        data_hash = _data_hash(content.data)

        cursor =  connection.execute(
            "INSERT INTO history (mime, data, data_hash, hostname, ip) VALUES (?, ?, ?, ?, ?)",
            (content.mime, content.data, data_hash, content.hostname, content.ip),
        )

        connection.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error('Error while add to history: [{}]', e)
        raise e


async def add_to_history(connection: sqlite3.Connection, content: Clipboard) -> int:
    async with _WRITE_DATABASE_LOCK:
        return await asyncio.to_thread(_add_to_history, connection, content)


def get_from_history(connection: sqlite3.Connection, id: int) -> Clipboard | None:
    cursor = connection.execute('SELECT * FROM history WHERE id = ?', (id,),)
    row: sqlite3.Row | None = cursor.fetchone()

    if not row:
        return row

    return Clipboard(
        id=row['id'],
        mime=row['mime'],
        data=row['data'],
        hostname=row['hostname'],
        ip=row['ip'],
        created_at=row['created_at'],
    )


def has_by_data(connection: sqlite3.Connection, data: bytes) -> bool:
    data_hash = _data_hash(data)
    cursor = connection.execute('SELECT 1 FROM history WHERE data_hash = ? LIMIT 1', (data_hash,),)
    return cursor.fetchone() is not None


def get_history(
    connection: sqlite3.Connection,
    limit: int = 30,
    created_at_sort: str = 'DESC'
) -> list[Clipboard]:
    cursor = connection.execute(
        f"SELECT * FROM history ORDER BY created_at {created_at_sort} LIMIT ?",
        (limit,),
    )

    rows: list[sqlite3.Row] = cursor.fetchall()
    output: list[Clipboard] = []

    for row in rows:
        output.append(Clipboard(
            id=row['id'],
            mime=row['mime'],
            data=row['data'],
            hostname=row['hostname'],
            ip=row['ip'],
            created_at=row['created_at'],
        ))

    return output


def _trim_history(connection: sqlite3.Connection, max_records: int = 1000) -> int:
    """
    Обрезает историю до max_records самых свежих записей.

    Возвращает количество удалённых записей (0, если чистить нечего).

    Логика:
      1. Быстро проверяем COUNT(*) — если записей <= лимита, выходим.
      2. Находим id «пороговой» записи — ровно max_records-й сверху
         (OFFSET max_records - 1 от начала DESC-сортировки по id).
      3. Удаляем всё, что строго старше этого id.
    """
    try:
        cursor = connection.execute("SELECT COUNT(*) FROM history")
        (count,) = cursor.fetchone()

        if count <= max_records:
            return 0

        cursor = connection.execute(
            "SELECT id FROM history ORDER BY id DESC LIMIT 1 OFFSET ?",
            (max_records - 1,),
        )

        row = cursor.fetchone()

        if row is None:
            # Защита от гонки: между COUNT и SELECT записей стало меньше.
            return 0

        threshold_id = row["id"]

        cursor = connection.execute(
            "DELETE FROM history WHERE id < ?",
            (threshold_id,),
        )

        connection.commit()

        return cursor.rowcount or 0
    except Exception as e:
        logger.error("Error while trim history: [{}]", e)
        raise e


async def trim_history(connection: sqlite3.Connection, max_records: int = 1000) -> int:
    async with _WRITE_DATABASE_LOCK:
        return await asyncio.to_thread(_trim_history, connection, max_records)
