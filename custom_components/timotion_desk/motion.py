"""Safety supervisor for desk movements.

The control box only keeps driving while it keeps receiving command frames
(like holding a handset button), so a movement is a loop: resend the frame,
look at the latest status, decide whether to go on. This module is that
decision, kept free of Bluetooth and Home Assistant so it can be tested
with scripted statuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .protocol import DeskStatus, Direction

SEND_INTERVAL = 0.1  # seconds between command frames (what the phone app does)

MAX_SECONDS_TARGET = 60.0
MAX_SECONDS_RESET = 45.0
NO_STATUS_SECONDS = 3.0
START_GRACE_SECONDS = 3.0
IDLE_CONFIRM_SECONDS = 1.0
RESET_IDLE_CONFIRM_SECONDS = 1.5
ARRIVAL_TOLERANCE_CM = 1


class MoveKind(StrEnum):
    """What we are asking the desk to do."""

    TARGET = "target"
    RESET = "reset"


class Outcome(StrEnum):
    """Result of one supervision step."""

    CONTINUE = "continue"
    DONE = "done"
    ABORT = "abort"


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome plus a human readable reason (set for ABORT)."""

    outcome: Outcome
    reason: str = ""


_CONTINUE = Decision(Outcome.CONTINUE)
_DONE = Decision(Outcome.DONE)


def _abort(reason: str) -> Decision:
    return Decision(Outcome.ABORT, reason)


class MoveSupervisor:
    """Decides, status by status, whether a movement may continue."""

    def __init__(
        self,
        kind: MoveKind,
        *,
        target_cm: int | None,
        start: DeskStatus,
        now: float,
    ) -> None:
        self._kind = kind
        self._target = target_cm
        self._started = now
        self._moved = False
        self._idle_since: float | None = None
        self._expected: Direction | None = None
        if kind is MoveKind.TARGET:
            if target_cm is None or start.height_cm is None:
                raise ValueError("a target move needs a target and a known start height")
            if target_cm > start.height_cm:
                self._expected = Direction.UP
            elif target_cm < start.height_cm:
                self._expected = Direction.DOWN

    def update(self, status: DeskStatus | None, status_age: float, now: float) -> Decision:
        """Judge the latest status. ``status_age`` is seconds since it arrived."""
        limit = MAX_SECONDS_TARGET if self._kind is MoveKind.TARGET else MAX_SECONDS_RESET
        if now - self._started > limit:
            return _abort("timed out")
        if status is None or status_age > NO_STATUS_SECONDS:
            return _abort("lost contact with the desk")

        if self._kind is MoveKind.TARGET:
            return self._update_target(status, now)
        return self._update_reset(status, now)

    def _update_target(self, status: DeskStatus, now: float) -> Decision:
        if status.reset_mode:
            return _abort("desk is in reset mode")
        if status.collision:
            return _abort("collision sensor triggered")
        assert self._target is not None and status.height_cm is not None

        if status.moving:
            if self._expected and status.direction is not self._expected:
                return _abort("desk is moving the wrong way")
            self._moved = True
            self._idle_since = None
            return _CONTINUE

        # Idle.
        arrived = abs(status.height_cm - self._target) <= ARRIVAL_TOLERANCE_CM
        if not self._moved and not arrived:
            if now - self._started > START_GRACE_SECONDS:
                return _abort("desk did not start moving")
            return _CONTINUE
        if self._idle_since is None:
            self._idle_since = now
        if now - self._idle_since >= IDLE_CONFIRM_SECONDS:
            return _DONE
        return _CONTINUE

    def _update_reset(self, status: DeskStatus, now: float) -> Decision:
        # Collisions are expected: the reset drives into the lower end stop.
        if status.moving or status.reset_mode:
            self._moved = True
            self._idle_since = None
            return _CONTINUE
        if not self._moved:
            if now - self._started > START_GRACE_SECONDS + 2:
                return _abort("desk did not start the reset")
            return _CONTINUE
        if self._idle_since is None:
            self._idle_since = now
        if now - self._idle_since >= RESET_IDLE_CONFIRM_SECONDS:
            return _DONE
        return _CONTINUE
