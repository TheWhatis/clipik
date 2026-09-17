import os
import sys
import msgpack
import ipaddress
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, field_validator


class Clipboard(BaseModel):
    id: int | None = None
    mime: str
    data: bytes
    hostname: str
    ip: str
    created_at: datetime | None = None


class ClipboardContent(BaseModel):
    mime: str
    data: bytes


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
    data: bytes
    session: str
    hostname: str


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


class BaseConfig(BaseModel):
    allowed_ips: list[str] = []
    interfaces: list[str] = []

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


class ServerConfig(BaseConfig):
    port: int
    log_dir: Path
    log_level: str
    size_limit: int
    handshake_timeout: int
    database: Path


class ClientConfig(BaseConfig):
    log_dir: Path
    log_level: str
    size_limit: int
    handshake_timeout: int
    database: Path


Config = ServerConfig | ClientConfig
AnyEvent = HandshakeEvent | HandshakeAckEvent | ClipboardEvent


_EVENT_BY_TYPE = {
    'handshake': HandshakeEvent,
    'handshake_ack': HandshakeAckEvent,
    'clipboard': ClipboardEvent,
}


def event_to_bytes(event: AnyEvent) -> bytes:
    return msgpack.packb(event.model_dump(), use_bin_type=True)


def event_from_bytes(buf: bytes) -> AnyEvent:
    payload = msgpack.unpackb(buf, raw=False)
    cls = _EVENT_BY_TYPE.get(payload.get('event'))

    if cls is None:
        raise ValueError(f"Unknown event type: [{payload.get('type')!r}]")

    return cls(**payload)
