from typing import Literal
from pydantic import BaseModel
from clipik.variables import VERSION, PROTOCOL


class ClipboardContent(BaseModel):
    mime: str
    data: str | bytes


class HandshakeEvent(BaseModel):
    event: Literal['handshake'] = 'handshake'
    protocol: str = PROTOCOL
    version: str = VERSION


class HandshakeAckEvent(BaseModel):
    event: Literal['handshake_ack'] = 'handshake_ack'
    protocol: str = PROTOCOL
    version: str = VERSION


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
