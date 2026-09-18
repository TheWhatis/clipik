import json
import socket
from typing import TYPE_CHECKING
import psutil
import asyncio
import argparse
import ipaddress
from loguru import logger
from packaging.version import Version
from .model import Config, Clipboard, ClipboardContent
from .database import get_history, get_from_history

if TYPE_CHECKING:
    from .container import Contaier


def is_ip_allowed(config: Config, ip: str) -> bool:
    if not config.allowed_ips:
        return True

    addr = ipaddress.ip_address(ip)

    for entry in config.allowed_ips:
        if '/' in entry:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        else:
            if addr == ipaddress.ip_address(entry):
                return True

    return False


def get_default_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def get_ips_by_interface(names: list[str]) -> list[str]:
    addrs = psutil.net_if_addrs()
    result = []
    for name in names:
        for addr in addrs.get(name, []):
            if addr.family == socket.AF_INET:
                result.append(addr.address)
    return result


def supports_versions(event_version: str, current_version) -> bool:
    return Version(event_version) >= Version(current_version)


def _raw_content(content: Clipboard):
    print(f"[{content.id}] {content.hostname} {content.data[:99]} ({len(content.data)} bytes)")


def list_contents(container: "Container", args: argparse.Namespace):
    history = get_history(container.db_connection, limit=args.limit)

    if args.format == 'json':
        print(json.dumps(history, indent=2))
        return

    if len(history) == 0:
        print("History is empty")
        return

    for content in history:
        _raw_content(content)


def first_contents(container: "Container", args: argparse.Namespace):
    history = get_history(container.db_connection, limit=1, created_at_sort='DESC')

    if len(history) == 0:
        print("History is empty")
        return

    if args.format == 'json':
        print(json.dumps(history[0], indent=2))
        return

    _raw_content(history[0])


def last_contents(container: "Container", args: argparse.Namespace):
    history = get_history(container.db_connection, limit=1, created_at_sort='ASC')

    if len(history) == 0:
        print("History is empty")
        return

    if args.format == 'json':
        print(json.dumps(history[0], indent=2))
        return

    _raw_content(history[0])


async def paste_clipboard(container: "Container", args: argparse.Namespace):
    clipboard = await asyncio.to_thread(
        get_from_history,
        container.db_connection,
        args.id,
    )

    if not clipboard:
        print(f"Clipboard with [{args.id}] not found")
        exit(1)

    await container.set_clipboard(ClipboardContent(
        mime=clipboard.mime,
        data=clipboard.data,
    ))
