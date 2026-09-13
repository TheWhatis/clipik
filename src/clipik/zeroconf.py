import os
import socket
import asyncio
from typing import TYPE_CHECKING
from loguru import logger
from collections.abc import AsyncGenerator
from clipik.model import LoseServiceEvent, NewServiceEvent
from zeroconf import ServiceInfo, Zeroconf, ServiceListener

if TYPE_CHECKING:
    from clipik.container import Container


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

    def add_service(self, zc: Zeroconf, type_, name):
        info = zc.get_service_info(type_, name)

        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])

            if ip.startswith('127.'):
                return

            if ip == self.container.local_ip:
                logger.debug(
                    'Local service registered: [{}] at [{}:{}]',
                    name,
                    ip,
                    info.port
                )

                return

            asyncio.run_coroutine_threadsafe(
                self.queue.put(NewServiceEvent(
                    name=name,
                    ip=ip,
                    host=ip,
                    port=info.port,
                )),
                self.loop,
            )

            logger.debug('New service [{}] at [{}:{}]', name, ip, info.port)

    def remove_service(self, zc: Zeroconf, type_, name):
        info = zc.get_service_info(type_, name)

        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])

            if ip.startswith('127.'):
                return

            asyncio.run_coroutine_threadsafe(
                self.queue.put(LoseServiceEvent(
                    name=name,
                    ip=ip,
                    host=ip,
                    port=info.port,
                )),
                self.loop
            )

            logger.debug('Lose service [{}]', name)

    def update_service(self, zc: Zeroconf, type_, name):
        pass


def get_zeroconf(local_ip: str) -> Zeroconf:
    return Zeroconf(interfaces=[local_ip])


def register_service(container: "Container"):
    INFO = ServiceInfo(
        container.service_type,
        f"{container.service_name}.{container.service_type}",
        addresses=[socket.inet_aton(container.local_ip)],
        port=container.config.port,
        properties={'version': container.version},
    )

    container.zeroconf.register_service(INFO)
    logger.info(
        'Registered service: [{}] at [{}:{}]',
        container.service_name,
        container.local_ip,
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
