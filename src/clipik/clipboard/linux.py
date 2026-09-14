import os
import shutil
import asyncio
from pathlib import Path
from asyncio.subprocess import Process
from collections.abc import AsyncGenerator
from clipik.model import ClipboardContent
from clipik.logger import logger


_HAS_WAYLAND = os.getenv('WAYLAND_DISPLAY', default=False)

if _HAS_WAYLAND:
    _HAS_WAYLAND=True


# X11-атом -> MIME
_X11_ATOM_TO_MIME: dict[str, str] = {
    'UTF8_STRING':   'text/plain;charset=utf-8',
    'STRING':        'text/plain;charset=latin-1',
    'TEXT':          'text/plain',
    'COMPOUND_TEXT': 'text/plain;charset=compound-text',
}

# MIME -> X11-атом (обратный маппинг)
_MIME_TO_X11_ATOM: dict[str, str] = {v: k for k, v in _X11_ATOM_TO_MIME.items()}

# Служебные атомы, которые не являются полезными данными
_X11_IGNORED: set[str] = {
    'TARGETS', 'MULTIPLE', 'TIMESTAMP', 'DELETE',
    'INSERT_SELECTION', 'INSERT_PROPERTY', 'SAVE_TARGETS',
    'LENGTH', 'FILE_NAME', 'HOST_NAME', 'CHARACTER_POSITION',
    'LINE_NUMBER', 'COLUMN_NUMBER', 'OWNER_OS', 'USER', 'CLASS',
    'NAME', 'ATOM', 'INTEGER', 'PIXMAP', 'BITMAP', 'DRAWABLE',
    'WINDOW', 'COLORMAP', 'BACKGROUND', 'FOREGROUND', 'FONT',
}

_TEXT_TYPE_ALIASES: set[str] = {
    'UTF8_STRING',
    'STRING',
    'TEXT',
    'COMPOUND_TEXT',
}

_TEXT_MIMES: set[str] = {
    'text/plain',
    'text/plain;charset=utf-8',
    'text/plain;charset=latin-1',
}

# Приоритет выбора target'а из доступных
_PREFERRED_TARGETS: list[str] = [
    'image/png',
    'image/jpeg',
    'image/bmp',
    'text/html',
    'text/plain;charset=utf-8',
    'text/plain',
    'UTF8_STRING',
    'STRING',
    'TEXT',
]

# Кэш живых дисплеев: display -> monotonic-время последней проверки
_ALIVE_CACHE: dict[str, float] = {}
_ALIVE_TTL: float = 10.0


def _sanitize_mime(mime: str) -> str:
    """Любой Wayland/X11 type → настоящий MIME."""
    if not mime:
        return 'text/plain;charset=utf-8'
    if mime in _TEXT_TYPE_ALIASES:
        return _X11_ATOM_TO_MIME.get(mime, 'text/plain;charset=utf-8')
    if '/' in mime:
        return mime
    # не MIME и не известный алиас — считаем текстом
    return 'text/plain;charset=utf-8'


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
        'wl-paste', '--no-newline', '--type', mime,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if stderr:
        logger.warning('wayland: wl-paste --no-newline --type [{}] stderr: [{}]', mime, stderr.decode())

    return stdout


async def _write_data_wayland(mime: str, data: bytes):
    mime = _sanitize_mime(mime)

    try:
        if mime in _TEXT_MIMES:
            cmd = ['wl-copy']
        else:
            cmd = ['wl-copy', '--type', mime]

        logger.debug('Executing {}', ' '.join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        proc.stdin.write(data)
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        logger.info('wayland: wrote [{}] bytes as [{}]', len(data), mime)
    except Exception as e:
        logger.error('wayland: failed to write data: [{}]', e)


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

        logger.debug('wayland: get types for clipboard: [{}]', types)
        if not types:
            logger.warning('wayland: no types available')
            continue

        chosen: str = next((p for p in _PREFERRED_TARGETS if p in types), None)
        if chosen is None:
            chosen = next((t for t in types if '/' in t), types[0])

        try:
            raw: bytes = await _read_data_wayland(chosen)
        except Exception as e:
            logger.error('wayland: failed to read [{}]: [{}]', chosen, e)
            continue

        yield ClipboardContent(
            mime=_sanitize_mime(chosen),
            data=raw,
        )


async def _is_duplicate_clipboard_wayland(content: ClipboardContent) -> bool:
    if not content.data:
        return False

    types = await _get_types_wayland()
    if not types:
        return False

    sanitized = _sanitize_mime(content.mime)

    for t in types:
        if _sanitize_mime(t) == sanitized:
            raw = await _read_data_wayland(t)
            return raw == content.data

    return False


async def _set_clipboard_wayland(content: ClipboardContent):
    logger.debug('Executing set_clipboard')
    if not content.data:
        logger.warning('Empty content.data')
        return

    if await _is_duplicate_clipboard_wayland(content):
        logger.warning('Received wayland clipboard content is duplicate')
        return

    await _write_data_wayland(content.mime, content.data)


def _find_x_displays() -> list[str]:
    """Все X-серверы по сокетам /tmp/.X11-unix/X*."""
    sock_dir = Path('/tmp/.X11-unix')
    if not sock_dir.is_dir():
        return []

    displays: list[str] = []
    for entry in sock_dir.iterdir():
        name = entry.name
        if name.startswith('X') and name[1:].isdigit():
            displays.append(f":{name[1:]}")
    return displays


def _x_env(display: str) -> dict[str, str]:
    return {**os.environ, 'DISPLAY': display}


def _x11_mime_for(target: str) -> str | None:
    """X11-атом -> MIME. None если это не полезные данные."""
    if target in _X11_IGNORED:
        return None
    if target in _X11_ATOM_TO_MIME:
        return _X11_ATOM_TO_MIME[target]
    if '/' in target:
        return target
    return None


def _x11_target_for_mime(mime: str) -> str:
    """MIME -> X11-атом. Если маппинга нет - отдаём как есть."""
    return _MIME_TO_X11_ATOM.get(mime, mime)


async def _x11_alive(display: str) -> bool:
    """Read-only проверка, что X-сервер отвечает. Не трогает клипборд."""
    import time

    now = time.monotonic()
    cached = _ALIVE_CACHE.get(display)
    if cached is not None and (now - cached) < _ALIVE_TTL:
        return True

    env = _x_env(display)
    try:
        proc = await asyncio.create_subprocess_exec(
            'xdpyinfo',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        await asyncio.wait_for(proc.wait(), timeout=2)
        alive = proc.returncode == 0
    except (asyncio.TimeoutError, OSError):
        alive = False

    if alive:
        _ALIVE_CACHE[display] = now
    else:
        _ALIVE_CACHE.pop(display, None)

    return alive


async def _x11_targets(display: str) -> list[str]:
    """Список TARGETS на дисплее. Пустой список, если буфер пуст/сервер мёртв."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'xclip', '-o', '-selection', 'clipboard', '-t', 'TARGETS',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_x_env(display),
        )

        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)

        return stdout.decode(errors='replace').split()
    except (asyncio.TimeoutError, OSError):
        return []


async def _x11_read(display: str, target: str) -> bytes | None:
    """Прочитать данные по target'у."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'xclip', '-o', '-selection', 'clipboard', '-t', target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_x_env(display),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout or None
    except (asyncio.TimeoutError, OSError):
        return None


async def _x11_write(display: str, target: str, data: bytes) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            'xclip', '-selection', 'clipboard', '-t', target, '-i',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=_x_env(display),
            start_new_session=True,
        )
        proc.stdin.write(data)
        await proc.stdin.drain()
        proc.stdin.close()

        # xclip форкается. Если он вышел сам — хорошо,
        # если продолжает висеть — это ожидаемо, не убиваем.
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        return True
    except Exception as e:
        logger.error('x11 [{}]: write failed: [{}]', display, e)
        return False


async def _x11_has_content(display: str, content: ClipboardContent) -> bool:
    """Лежит ли на этом дисплее ровно этот контент."""
    if not content.data:
        return False

    target = _x11_target_for_mime(content.mime)
    targets = await _x11_targets(display)
    if target not in targets:
        return False

    raw = await _x11_read(display, target)
    if raw is None:
        return False

    return raw == content.data


async def _x11_pick_target(display: str) -> tuple[str, str] | None:
    """Выбрать (target, mime) на дисплее по приоритету. None если нечего брать."""
    targets = await _x11_targets(display)
    if not targets:
        return None

    for preferred in _PREFERRED_TARGETS:
        if preferred in targets:
            mime = _x11_mime_for(preferred)
            if mime is not None:
                return preferred, mime

    for target in targets:
        mime = _x11_mime_for(target)
        if mime is not None:
            return target, mime

    return None


async def _listen_one_x11(
    display: str,
    size_limit: int,
) -> AsyncGenerator[ClipboardContent, None]:
    """Слушает один X-сервер через clipnotify."""
    while True:
        try:
            notify = await asyncio.create_subprocess_exec(
                'clipnotify',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=_x_env(display),
            )

            await notify.wait()
        except OSError as e:
            logger.error('x11 [{}]: clipnotify failed: [{}]', display, e)
            await asyncio.sleep(1)
            continue
        except asyncio.CancelledError:
            raise

        picked = await _x11_pick_target(display)
        if picked is None:
            continue

        target, mime = picked
        raw = await _x11_read(display, target)
        if not raw:
            continue

        if len(raw) > size_limit:
            logger.warning(
                'x11 [{}]: content size [{}] exceeds limit [{}], skip',
                display, len(raw), size_limit,
            )
            continue

        yield ClipboardContent(
            mime=mime,
            data=raw,
        )


async def _pump(gen, queue: asyncio.Queue):
    try:
        async for item in gen:
            await queue.put(item)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error('x11: pump failed: [{}]', e)


async def _listen_clipboard_x11(
    size_limit: int,
) -> AsyncGenerator[ClipboardContent, None]:
    """Слушает все живые X-серверы. Мёртвые молча пропускает."""
    if shutil.which('xclip') is None or shutil.which('clipnotify') is None:
        logger.info('x11: xclip/clipnotify not found, backend disabled')
        return

    displays = _find_x_displays()
    if not displays:
        logger.info('x11: no X sockets found, backend disabled')
        return

    alive: list[str] = []
    for display in displays:
        if await _x11_alive(display):
            alive.append(display)
            logger.info('x11: display [{}] alive', display)
        else:
            logger.debug('x11: display [{}] skipped', display)

    if not alive:
        logger.info('x11: no live X servers, backend disabled')
        return

    queue: asyncio.Queue = asyncio.Queue()
    pumps: list[asyncio.Task] = [
        asyncio.create_task(_pump(_listen_one_x11(d, size_limit), queue))
        for d in alive
    ]

    try:
        while True:
            content = await queue.get()
            yield content
    finally:
        for task in pumps:
            task.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)


async def _is_duplicate_clipboard_x11(content: ClipboardContent) -> bool:
    """True если контент лежит хотя бы на одном живом X-сервере."""
    if not content.data:
        return False

    displays = _find_x_displays()
    for display in displays:
        if not await _x11_alive(display):
            continue
        if await _x11_has_content(display, content):
            return True

    return False


async def _set_clipboard_x11(content: ClipboardContent):
    """Пишет контент во все живые X-серверы, где его ещё нет."""
    if not content.data:
        return

    if await _is_duplicate_clipboard_x11(content):
        logger.debug('x11: content already present on some display, checking per-display')
    else:
        logger.debug('x11: content not present anywhere')

    displays = _find_x_displays()
    if not displays:
        return

    raw = content.data

    # отбираем только живые, и только те, где ещё нет этого контента
    need_write: list[str] = []
    for display in displays:
        if not await _x11_alive(display):
            continue
        if await _x11_has_content(display, content):
            logger.debug('x11 [{}]: already has content, skip', display)
            continue
        need_write.append(display)

    if not need_write:
        logger.debug('x11: all live displays already have this content')
        return

    target = _x11_target_for_mime(content.mime)

    results = await asyncio.gather(
        *[_x11_write(d, target, raw) for d in need_write],
        return_exceptions=True,
    )

    for display, result in zip(need_write, results):
        if isinstance(result, Exception):
            logger.error('x11 [{}]: write exception: [{}]', display, result)
        elif not result:
            logger.warning('x11 [{}]: write failed', display)
        else:
            logger.info(
                'x11 [{}]: wrote [{}] bytes as [{}]',
                display, len(raw), target,
            )


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

    coros.append(_set_clipboard_x11(content))

    if _HAS_WAYLAND:
        coros.append(_set_clipboard_wayland(content))


    await asyncio.gather(*coros)
