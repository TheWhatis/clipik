import asyncio
from asyncio.subprocess import Process
import base64
from collections.abc import AsyncGenerator
from clipik.model import ClipboardContent
from clipik.logger import logger


async def _get_types() -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        'wl-paste', '--list-types',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if stderr:
        logger.warning('wayland: wl-paste --list-types stderr: [{}]', stderr.decode)

    return stdout.decode(errors='replace').split()


async def _read_data(mime: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        'wl-paste', '--type', mime,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if stderr:
        logger.warning('wayland: wl-paste --type () stderr: [{}]', mime, stderr.decode())

    return stdout


async def _write_data(mime, str, data: bytes):
    try:
        proc = await asyncio.create_subprocess_exec(
            'wl-copy', '--type', mime,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate(data)

        if stderr:
            logger.warning('wayland: wl-copy --type {} stderr: [{}]', mime, stderr.decode())
    except Exception as e:
        logger.error('wayland: failed to write data', e)


async def _process_watch() -> Process:
    while True:
        try:
            return await asyncio.create_subprocess_exec(
                'wl-paste', '--watch', 'sh', '-c', 'base64 -w0; echo',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error('wayland: failed to start wl-paste --watch: [{}]', e)
            continue


async def listen_clipboard() -> AsyncGenerator[ClipboardContent, None]:
    logger.debug('Started listen_clipboard wayland')
    process = await _process_watch()

    while True:
        try:
            try:
                line = await process.stdout.readline()
            except Exception as e:
                logger.error('wayland: readline failed: [{}]', e)
                continue
        except Exception as e:
            logger.error('wayland: wl-paste --watch read error: [{}]', e)

        logger.debug('wayland: wl-paste watch line: [{}]', line)
        if not line and process.returncode is not None:
            logger.error('wayland: wl-paste --watch exited with code [{}]', process.returncode)
            continue

        try:
            types: list[str] = await _get_types()
        except Exception as e:
            logger.error('wayland: failed to get types [{}]', e)
            continue

        logger.debug('Get types for clipboard: [{}]', types)
        if not types:
            logger.warning('wayland: no types available')
            continue

        preferred: list[str] = [
            'image/png',
            'image/jpeg',
            'image/bmp',
            'text/plain',
            'text/html',
        ]

        chosen: str = next((p for p in preferred if p in types), types[0])

        try:
            raw: bytes = await _read_data(chosen)
        except Exception as e:
            logger.error('wayland: failed to read [{}]: [{}]', chosen, e)
            continue

        yield ClipboardContent(
            mime=chosen,
            data=base64.b64encode(raw).decode()
        )


async def set_clipboard(content: ClipboardContent):
    if not content.data:
        return

    raw: bytes = content.data

    if isinstance(content.data, str):
        raw = base64.b64decode(content.data)

    await _write_data(content.mime, raw)


async def is_duplicate_clipboard(content: ClipboardContent) -> bool:
    """Проверяет, что переданное содержимое уже находится в буфере обмена."""
    if not content.data:
        return False

    types: list[str] = await _get_types()
    if content.mime not in types:
        return False

    raw: bytes = await _read_data(content.mime)
    current_b64: str = base64.b64encode(raw).decode()

    return current_b64 == content.data
