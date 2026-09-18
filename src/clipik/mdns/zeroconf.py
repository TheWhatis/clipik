import psutil
import socket
import ipaddress
import asyncio
from typing import TYPE_CHECKING
from loguru import logger
from collections.abc import AsyncGenerator
from zeroconf import IPVersion, InterfaceChoice, ServiceInfo, Zeroconf, ServiceListener
from ..model import LoseServiceEvent, NewServiceEvent
from ..functions import get_default_ip


if TYPE_CHECKING:
    from ..container import Container


def _addr_to_str(packed: bytes) -> str:
    if len(packed) == 4:
        return str(ipaddress.IPv4Address(packed))
    if len(packed) == 16:
        return str(ipaddress.IPv6Address(packed))
    raise ValueError(f'Unexpected address length: {len(packed)}')


class _ServiceListener(ServiceListener):
    def __init__(
        self,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        container: "Container",
    ):
        self.queue = queue
        self.loop = loop
        self.container = container
        self.own_name = f"{container.service_name}.{container.service_type}"
        self._cache: dict[str, ServiceInfo] = {}

    def _emit(self, event_cls, name: str, info: ServiceInfo):
        for packed in info.addresses:
            ip = _addr_to_str(packed)
            asyncio.run_coroutine_threadsafe(
                self.queue.put(event_cls(
                    name=name,
                    ip=ip,
                    host=ip,
                    port=info.port,
                )),
                self.loop,
            )

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        info = zc.get_service_info(type_, name)
        if not info:
            logger.warning('add_service: info is None for [{}]', name)
            return
        self._cache[name] = info
        self._emit(NewServiceEvent, name, info)
        logger.debug('New service [{}]', name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        info = self._cache.pop(name, None)
        if info is None:
            logger.debug('remove_service: no cached info for [{}]', name)
            return
        self._emit(LoseServiceEvent, name, info)
        logger.debug('Lose service [{}]', name)

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        logger.debug('Update service [{}]', name)


def get_zeroconf(interfaces: list[str]) -> Zeroconf:
    interfaces_inp = InterfaceChoice.Default

    if interfaces:
        interfaces_inp = []
        for interface in interfaces:
            addrs = psutil.net_if_addrs(interface, [])

            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue

                interfaces_inp.append(addr.address)

    return Zeroconf(
        interfaces=interfaces_inp,
        ip_version=IPVersion.V4Only,
    )


def _all_ipv4_addresses() -> list[bytes]:
    """Все не-loopback IPv4 адреса машины, в packed виде."""
    addrs: list[bytes] = []

    # через hostname
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                addrs.append(socket.inet_aton(ip))
    except OSError:
        pass

    # через connect к приватному адресу (без интернета)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith('127.'):
            packed = socket.inet_aton(ip)
            if packed not in addrs:
                addrs.append(packed)
    except OSError:
        pass

    return addrs


def register_service(container: "Container"):
    addresses = _all_ipv4_addresses()

    info = ServiceInfo(
        container.service_type,
        f"{container.service_name}.{container.service_type}",
        addresses=addresses,
        port=container.config.port,
        properties={'version': container.version},
    )

    container.zeroconf.register_service(info)

    logger.info(
        'Registered service: [{}] at [{}] port in all available interfaces',
        container.service_name,
        container.config.port
    )


def unregister_service(container: "Container"):
    container.zeroconf.unregister_all_services()
    container.zeroconf.close()
    logger.info('Unregistered service')


async def discover_services(
    container: "Container"
) -> AsyncGenerator[NewServiceEvent | LoseServiceEvent, None]:
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    listener = _ServiceListener(queue, loop, container)
    container.zeroconf.add_service_listener(container.service_type, listener)

    try:
        while True:
            event = await queue.get()
            yield event
    finally:
        container.zeroconf.remove_service_listener(listener)
