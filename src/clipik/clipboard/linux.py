import os
import asyncio
from asyncio.subprocess import Process
import base64
from collections.abc import AsyncGenerator
import subprocess
from clipik.model import ClipboardContent, Config
from clipik.logger import logger


_HAS_WAYLAND = os.getenv('WAYLAND_DISPLAY', default=False)

if _HAS_WAYLAND:
    _HAS_WAYLAND=True


async def _get_types_wayland() -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        'wl-paste', '--list-types',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if stderr:
        logger.warning('wayland: wl-paste --list-types stderr: [{}]', stderr.decode())
        return []

    return stdout.decode().splitlines()


async def _read_data_wayland(mime: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        'wl-paste', '--type', mime,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if stderr:
        logger.warning('wayland: wl-paste --type () stderr: [{}]', mime, stderr.decode())

    return stdout


async def _write_data_wayland(mime: str, data: bytes):
    try:
        logger.debug('Executing wl-copy --type [{}]', mime)
        proc = await asyncio.create_subprocess_exec(
            'wl-copy', '--type', mime, '--paste-once',
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        logger.debug('Awaiting communicate wl-copy --type [{}] --paste-once', mime)
        _, stderr = await proc.communicate(data)

        if stderr:
            logger.warning(
                'wayland: wl-copy --type [{}] --paste-once stderr: [{}]',
                mime,
                stderr.decode()
            )
        else:
            logger.info(
                'Successfully pasted ({} bytes) to clipboard wl-copy --type [{}] --paste-once',
                len(data),
                mime
            )
    except Exception as e:
        logger.error('wayland: failed to write data', e)


async def _process_watch_wayland(size_limit: int) -> Process:
    while True:
        try:
            return await asyncio.create_subprocess_exec(
                'wl-paste', '--watch', 'sh', '-c', 'base64 -w0; echo',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=size_limit,
            )
        except Exception as e:
            logger.error('wayland: failed to start wl-paste --watch: [{}]', e)
            continue


async def _listen_clipboard_wayland(size_limit: int) -> AsyncGenerator[ClipboardContent, None]:
    logger.debug('Started listen_clipboard wayland')
    process = await _process_watch_wayland(size_limit)

    while True:
        try:
            try:
                line = await process.stdout.readline()
            except Exception as e:
                logger.error('wayland: readline failed: [{}]', e)
                continue
        except Exception as e:
            logger.error('wayland: wl-paste --watch read error: [{}]', e)

        logger.debug('wayland: wl-paste watch line: ({} bytss)', len(line))

        if not line or line == b'\n':
            if process.returncode is not None:
                logger.error('wayland: wl-paste --watch exited with code [{}]', process.returncode)
                process = await _process_watch_wayland()

            continue

        try:
            types: list[str] = await _get_types_wayland()

            if not types:
                logger.warning('wayland: types list is empty [{}]', types)
                continue
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
            raw: bytes = await _read_data_wayland(chosen)
        except Exception as e:
            logger.error('wayland: failed to read [{}]: [{}]', chosen, e)
            continue

        yield ClipboardContent(
            mime=chosen,
            data=base64.b64encode(raw).decode()
        )


async def _is_duplicate_clipboard_wayland(content: ClipboardContent) -> bool:
    """Проверяет, что переданное содержимое уже находится в буфере обмена."""
    if not content.data:
        return False

    types: list[str] = await _get_types_wayland()

    if content.mime not in types:
        return False

    raw: bytes = await _read_data_wayland(content.mime)
    current_b64: str = base64.b64encode(raw).decode()

    return current_b64 == content.data


async def _set_clipboard_wayland(content: ClipboardContent):
    logger.debug('Executing set_clipboard')
    if not content.data:
        logger.warning('Empty content.data')
        return

    if await _is_duplicate_clipboard_wayland(content):
        logger.warning('Received wayland clipboard content is duplicate')
        return

    raw: bytes = content.data

    if isinstance(content.data, str):
        logger.info('Content.data is str', content.data)
        raw = base64.b64decode(content.data)

    await _write_data_wayland(content.mime, raw)


async def _listen_clipboard_x11(size_limit: int) -> AsyncGenerator[ClipboardContent, None]:
    while True:
        try:
            await asyncio.to_thread(subprocess.run, ['clipnotify'], check=True)
        except subprocess.CalledProcessError as e:
            logger.error('x11: clipnotify failed: [{}]', e)
            await asyncio.sleep(0.1)
            continue

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ['xclip', '-o', '-selection', 'clipboard', '-t', 'targets'],
                capture_output=True,
                text=True,
            )

            targets: list[str] = result.stdout.strip().split()
        except Exception as e:
            logger.error('x11: failed to get targets: [{}]', e)
            await asyncio.sleep(0.1)
            continue

        if not targets:
            yield ClipboardContent(mime='text/plain', data='')
            continue

        preferred: list[str] = [
            'mage/png'
            'mage/jpeg'
            'mage/bmp'
            'ext/plain'
            'TF8_STRING'
            'TRING'
        ]

        chosen: str = next((p for p in preferred if p in targets), targets[0])

        try:
            raw: bytes = await asyncio.to_thread(
                lambda: subprocess.run(
                    ['xclip', '-o', '-selection', 'clipboard', '-t', chosen],
                    capture_output=True
                ).stdout
            )
        except Exception as e:
            logger.error('x11: failed to read clipboard: [{}]', e)
            continue

        yield ClipboardContent(
            mime=chosen,
            data=base64.b64encode(raw).decode(),
        )


async def _is_duplicate_clipboard_x11(content: ClipboardContent) -> bool:
    """Проверяет, что переданное содержимое уже находится в буфере обмена."""
    if not content.data:
        return False

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ['xclip', '-o', '-selection', 'clipboard', '-t', 'TARGETS'],
            capture_output=True,
            text=True,
        )
        targets: list[str] = result.stdout.strip().split()
    except Exception as e:
        logger.error('x11: failed to get targets: [{}]', e)
        return False

    if content.mime not in targets:
        return False

    try:
        raw: bytes = await asyncio.to_thread(
            lambda: subprocess.run(
                ['xclip', '-o', '-selection', 'clipboard', '-t', content.mime],
                capture_output=True
            ).stdout
        )
    except Exception as e:
        logger.error('x11: failed to read clipboard: [{}]', e)
        return False

    current_b64: str = base64.b64encode(raw).decode()
    return current_b64 == content.data


async def _set_clipboard_x11(content: ClipboardContent):
    if not content.data:
        return

    if await _is_duplicate_clipboard_x11(content):
        logger.warning('Received X11 clipboard content is duplicate ')
        return

    try:
        raw: bytes = content.data

        if isinstance(content.data, str):
            raw = base64.b64decode(content.data)

        await asyncio.to_thread(
            subprocess.run,
            ['xclip', '-selection', 'clipboard', '-t', content.mime],
            input=raw,
        )
    except Exception as e:
        logger.error('x11: failed to set clipboard: [{}]', e)


async def _pump(gen, queue):
    async for item in gen:
        await queue.put(item)


async def listen_clipboard(size_limit: int) -> AsyncGenerator[ClipboardContent, None]:
    queue: asyncio.Queue = asyncio.Queue()
    tasks: set[asyncio.Task] = set()

    if _HAS_WAYLAND:
        tasks.add(asyncio.create_task(_pump(_listen_clipboard_wayland(size_limit), queue)))

    tasks.add(asyncio.create_task(_pump(_listen_clipboard_x11(size_limit), queue)))

    try:
        while True:
            yield await queue.get()
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)


async def set_clipboard(content: ClipboardContent):
    coros = []

    if _HAS_WAYLAND:
        coros.append(_set_clipboard_wayland(content))

    coros.append(_set_clipboard_x11(content))

    await asyncio.gather(*coros)
