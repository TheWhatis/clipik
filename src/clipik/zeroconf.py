import os
import socket
import asyncio
from collections.abc import AsyncGenerator
from clipik.model import LoseServiceEvent, NewServiceEvent
from zeroconf import ServiceInfo, Zeroconf, ServiceListener
from clipik.variables import VERSION, PEER_PORT
from clipik.logger import logger


def _get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    return ip



SERVICE_NAME = f"clipik-{socket.gethostname()}"
SERVICE_TYPE = '_clipik._tcp.local.'
LOCAL_IP = _get_local_ip()


INFO = ServiceInfo(
    SERVICE_TYPE,
    f"{SERVICE_NAME}.{SERVICE_TYPE}",
    addresses=[socket.inet_aton(LOCAL_IP)],
    port=PEER_PORT,
    properties={'version': VERSION},
)


class _ServiceListener(ServiceListener):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop

    def add_service(self, zc: Zeroconf, type_, name):
        info = zc.get_service_info(type_, name)

        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])

            if ip.startswith('127.'):
                return

            if ip == LOCAL_IP:
                logger.debug('Local service registered: [{}] at [{}:{}]', name, ip, info.port)
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

    def update_service(self, zc, type_, name):
        pass


def get_zeroconf() -> Zeroconf:
    return Zeroconf(interfaces=[LOCAL_IP])


def register_service(zc: Zeroconf):
    zc.register_service(INFO)
    logger.info('Registered service: [{}] at [{}:{}]', SERVICE_NAME, LOCAL_IP, PEER_PORT)


def unregister_service(zc: Zeroconf):
    zc.unregister_all_services()
    zc.close()
    logger.info('Unregistered service')


async def discover_services(zc: Zeroconf) -> AsyncGenerator[NewServiceEvent | LoseServiceEvent, None]:
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    listener = _ServiceListener(queue, loop)
    zc.add_service_listener(SERVICE_TYPE, listener)

    try:
        while True:
            event = await queue.get()
            yield event
    finally:
        zc.remove_service_listener(zc)
