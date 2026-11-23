"""Frame codec for TiMotion TWD1 Bluetooth modules ("protocol 1").

Pure Python on purpose: no Home Assistant imports, so it can be unit tested
with the plain standard library. See docs/PROTOCOL.md for how each rule was
established.

The module exposes a Nordic UART style service. We write 5 byte command
frames and receive 5 byte status frames:

    command  D9 FF <cmd> <arg> <sum>
    status   99 <status> <height hi> <height lo> <sum>

``sum`` is the sum of the first four bytes masked with 0x7F (not 0xFF).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # desk -> host
WRITE_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # host -> desk

DEVICE_NAME_PREFIX = "stand UP-"

# Factory travel of the desks this was developed on. The control box enforces
# its own limits; these only bound what we are willing to ask for.
HEIGHT_MIN_CM = 65
HEIGHT_MAX_CM = 130

CHECKSUM_MASK = 0x7F

_TX_HEAD = (0xD9, 0xFF)
_RX_HEAD = 0x99
_PROTOCOL2_HEAD = 0x9D

CMD_STOP = 0x00
CMD_UP = 0x01
CMD_DOWN = 0x02
CMD_RESET = 0x03
CMD_TARGET = 0x04

# Status byte: bit 6 is always set. Bits 0/1 = moving down/up, bit 4 = the
# anti-collision sensor has triggered. 0x03 on its own (with the 0x01FF height
# sentinel) means the control box is in height-reset mode.
_STATUS_DOWN = 0x01
_STATUS_UP = 0x02
_STATUS_COLLISION = 0x10
_STATUS_RESET_MODE = 0x03
_HEIGHT_SENTINEL = 0x01FF
_HEIGHT_OFFSET = 256


def checksum(data: bytes) -> int:
    """Checksum over the first four bytes of a frame."""
    return sum(data[:4]) & CHECKSUM_MASK


def build_command(command: int, argument: int = 0) -> bytes:
    """Build a 5 byte command frame."""
    body = bytes((*_TX_HEAD, command, argument))
    return body + bytes((checksum(body),))


STOP_FRAME = build_command(CMD_STOP)
UP_FRAME = build_command(CMD_UP)
DOWN_FRAME = build_command(CMD_DOWN)
RESET_FRAME = build_command(CMD_RESET)


def valid_height(height_cm: int) -> bool:
    """Whether a target height is inside the range we will ever request."""
    return HEIGHT_MIN_CM <= height_cm <= HEIGHT_MAX_CM


def move_to_frame(height_cm: int) -> bytes:
    """Command the control box to drive to ``height_cm`` by itself."""
    if not valid_height(height_cm):
        raise ValueError(
            f"height must be between {HEIGHT_MIN_CM} and {HEIGHT_MAX_CM} cm"
        )
    return build_command(CMD_TARGET, height_cm)


class Direction(StrEnum):
    """Direction of travel reported by the desk."""

    IDLE = "idle"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class DeskStatus:
    """One decoded status frame."""

    height_cm: int | None  # None while the desk is in reset mode
    direction: Direction
    collision: bool
    reset_mode: bool
    raw: bytes = field(compare=False, repr=False, default=b"")

    @property
    def moving(self) -> bool:
        """True while the motors are running (also while reversing)."""
        return self.direction is not Direction.IDLE


def parse_status(data: bytes) -> DeskStatus | None:
    """Decode a status frame, or return None if it is not a valid one."""
    data = bytes(data)
    if len(data) != 5 or data[0] != _RX_HEAD or checksum(data) != data[4]:
        return None

    status = data[1]
    raw_height = (data[2] << 8) | data[3]

    if status == _STATUS_RESET_MODE or raw_height == _HEIGHT_SENTINEL:
        # In reset mode the height field is a sentinel (255 cm), not a height.
        return DeskStatus(
            height_cm=None,
            direction=_direction(status) if status != _STATUS_RESET_MODE else Direction.IDLE,
            collision=False,
            reset_mode=True,
            raw=data,
        )

    return DeskStatus(
        height_cm=raw_height - _HEIGHT_OFFSET,
        direction=_direction(status),
        collision=bool(status & _STATUS_COLLISION),
        reset_mode=False,
        raw=data,
    )


def is_protocol2_frame(data: bytes) -> bool:
    """Whether a frame belongs to the newer "protocol 2" (not supported here).

    Those modules send 11, 14 or 19 byte frames starting with 0x9D.
    """
    return len(data) in (11, 14, 19) and data[0] == _PROTOCOL2_HEAD and data[1] in (0, 1, 2)


def _direction(status: int) -> Direction:
    if status & _STATUS_UP:
        return Direction.UP
    if status & _STATUS_DOWN:
        return Direction.DOWN
    return Direction.IDLE
