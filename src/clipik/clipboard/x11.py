import asyncio
import base64
import subprocess
from collections.abc import AsyncGenerator
from clipik.model import ClipboardContent


async def listen_clipboard() -> AsyncGenerator[ClipboardContent, None]:
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
                ['xclip', '-o', '-selection', 'clipboard', '-t', 'targetse'],
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


async def set_clipboard(content: ClipboardContent):
    if not content.data:
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


async def is_duplicate_clipboard(content: ClipboardContent) -> bool:
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
