import sqlite3
import asyncio
import hashlib
from .model import Clipboard, Config


def initialize_database(config: Config) -> sqlite3.Connection:
    config.database.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection = sqlite3.connect(config.database)

    connection.execute("PRAGMA journal_mode = WAL")   # читатели не блокируют писателя
    connection.execute("PRAGMA synchronous = NORMAL") # быстрее, безопасно в WAL
    connection.execute("PRAGMA busy_timeout = 5000")  # ждать 5с при блокировке
    connection.execute("PRAGMA foreign_keys = ON")    # если нужны F

    connection.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        mime       TEXT NOT NULL,
        data       BLOB NOT NULL,
        data_hash  BLOG NOT NULL,
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


def _data_hash(data: bytes) -> bytes:
    return hashlib.sha256(data)


def add_to_history(connection: sqlite3.Connection, content: Clipboard) -> int:
    data_hash = _data_hash(content.data)

    cursor =  connection.execute(
        "INSERT INTO history (mime, data, data_hash, hostname, ip) VALUES (?, ?, ?, ?, ?)",
        (content.mime, content.data, data_hash, content.hostname, content.ip),
    )

    connection.commit()
    return cursor.lastrowid


def get_from_history(connection: sqlite3,Connection, id: int) -> Clipboard | None:
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


def get_history(connection: sqlite3.Connection, limit: int = 30, created_at_sort: str = 'DESC') -> list[Clipboard]:
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
