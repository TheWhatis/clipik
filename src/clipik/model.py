import os
from typing import Literal
from pydantic import BaseModel, field_validator
from clipik.enum import GraphicProtocol


class ClipboardContent(BaseModel):
    mime: str
    data: str | bytes


class HandshakeEvent(BaseModel):
    event: Literal['handshake'] = 'handshake'
    protocol: str
    version: str


class HandshakeAckEvent(BaseModel):
    event: Literal['handshake_ack'] = 'handshake_ack'
    protocol: str
    version: str


class ClipboardEvent(BaseModel):
    event: Literal['clipboard'] = 'clipboard'
    mime: str
    data: str


class NewServiceEvent(BaseModel):
    event: Literal['new_service'] = 'new_service'
    name: str
    ip: str
    host: str
    port: int


class LoseServiceEvent(BaseModel):
    event: Literal['lose_service'] = 'lose_service'
    name: str
    ip: str
    host: str
    port: int


class Config(BaseModel):
    graphic_protocol: GraphicProtocol | None = None
    port: int | None = None
    size_limit: int | None = None
    log_level: str | None = None
    handshake_timeout: int | None = None
    allowed_ips: list[str] | None = None

    @field_validator('allowed_ips')
    @classmethod
    def _check_allowed_ips(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        for entry in value:
            try:
                if '/' in entry:
                    ipaddress.ip_network(entry, strict=False)
                else:
                    ipaddress.ip_address(entry)
            except ValueError as e:
                raise ValueError(f"Invalid IP/CIDR [{entry!r}]: [{e}]") from e

        return value

    def resolve_properties(self) -> None:
        if not self.graphic_protocol:
            self.graphic_protocol = GraphicProtocol.detect()

        if not self.log_level:
            self.log_level = os.getenv('CLIPIK_LOG_LEVEL', default='INFO')

        if not self.port:
            self.port = int(os.getenv('CLIPIK_PORT', default=8765))

        if not self.size_limit:
            self.size_limit = int(os.getenv('CLIPIK_SIZE_LIMIT', default=64 * 1024 * 1024))

        if not self.handshake_timeout:
            self.handshake_timeout = int(os.getenv('CLIPIK_HANDSHAKE_TIMEOUT', default=7))

    def is_ip_allowed(self, ip: str) -> bool:
        if not self.allowed_ips:
            return True

        if self.allowed_ips is None:
            return True

        addr = ipaddress.ip_address(ip)
        for entry in self.allowed_ips:
            if '/' in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
                elif addr == ipaddress.ip_address(entry):
                    return True

        return False
