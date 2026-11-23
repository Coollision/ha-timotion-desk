"""Bluetooth connection and command handling for one desk."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    CONF_KEEP_CONNECTED,
    CONF_PRESET_HEIGHT,
    CONF_PRESET_NAME,
    CONF_PRESETS,
    DEFAULT_KEEP_CONNECTED,
    IDLE_DISCONNECT_SECONDS,
    RECONNECT_MIN_SECONDS,
)
from .motion import SEND_INTERVAL, MoveKind, MoveSupervisor, Outcome
from .protocol import (
    HEIGHT_MAX_CM,
    HEIGHT_MIN_CM,
    NOTIFY_CHAR_UUID,
    RESET_FRAME,
    STOP_FRAME,
    WRITE_CHAR_UUID,
    DeskStatus,
    is_protocol2_frame,
    move_to_frame,
    parse_status,
    valid_height,
)

_LOGGER = logging.getLogger(__name__)

BLE_ERRORS = (BleakError, TimeoutError, OSError)
FIRST_STATUS_TIMEOUT = 3.0


@dataclass(frozen=True, slots=True)
class Preset:
    """A named height."""

    name: str
    height: int


class TimotionDesk:
    """One desk: connection, last known status, and movement commands."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self.name: str = entry.title
        self.status: DeskStatus | None = None
        self.status_time = 0.0
        self.connected = False
        self.unsupported_protocol = False  # the desk answered in "protocol 2"
        self._closed = False  # set on unload: never reconnect after that
        self.target_cm: int | None = None  # set while a move is running

        self._client: BleakClient | None = None
        self._listeners: set[CALLBACK_TYPE] = set()
        self._connect_lock = asyncio.Lock()
        self._move_lock = asyncio.Lock()
        self._stop_requested = asyncio.Event()
        self._last_attempt = 0.0
        self._idle_handle: asyncio.TimerHandle | None = None
        self._cancel_advert: CALLBACK_TYPE | None = None

    # -- configuration -----------------------------------------------------

    @property
    def keep_connected(self) -> bool:
        return self.entry.options.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED)

    @property
    def presets(self) -> list[Preset]:
        return [
            Preset(item[CONF_PRESET_NAME], int(item[CONF_PRESET_HEIGHT]))
            for item in self.entry.options.get(CONF_PRESETS, [])
        ]

    # -- listeners ---------------------------------------------------------

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Register for status/connection changes; returns the remover."""
        self._listeners.add(update)
        return lambda: self._listeners.discard(update)

    @callback
    def _dispatch(self) -> None:
        for update in list(self._listeners):
            update()

    # -- lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        """Start watching for the desk and connect if configured to."""
        self._cancel_advert = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        if self.keep_connected:
            self._schedule_connect()

    async def async_shutdown(self) -> None:
        """Stop everything: advertisement watch, running move, connection."""
        self._closed = True
        if self._cancel_advert:
            self._cancel_advert()
            self._cancel_advert = None
        self._stop_requested.set()
        self._cancel_idle()
        await self._async_disconnect()

    # -- connection --------------------------------------------------------

    @callback
    def _async_on_advertisement(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        if self.keep_connected and not self.connected:
            self._schedule_connect()

    @callback
    def _schedule_connect(self) -> None:
        if (
            self._closed
            or self._connect_lock.locked()
            or monotonic() - self._last_attempt < RECONNECT_MIN_SECONDS
        ):
            return
        self._last_attempt = monotonic()
        self.entry.async_create_background_task(
            self.hass, self._async_try_connect(), f"{self.address} connect"
        )

    async def _async_try_connect(self) -> None:
        try:
            await self._async_connect()
        except HomeAssistantError as err:
            _LOGGER.debug("Could not connect to %s: %s", self.address, err)

    async def _async_connect(self) -> None:
        async with self._connect_lock:
            if self._closed:
                raise HomeAssistantError(f"{self.name} is being unloaded")
            if self._client is not None and self._client.is_connected:
                return
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise HomeAssistantError(
                    f"{self.name} is not in range of a Bluetooth adapter or proxy "
                    "(close the Stand Up Pls phone app, it can hold the only connection)"
                )
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    self._on_disconnected,
                    max_attempts=3,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    ),
                )
                await client.start_notify(NOTIFY_CHAR_UUID, self._on_notify)
                # The module only starts streaming status after its first write.
                await client.write_gatt_char(WRITE_CHAR_UUID, STOP_FRAME, response=False)
            except BLE_ERRORS as err:
                raise HomeAssistantError(f"Could not connect to {self.name}: {err}") from err
            self._client = client
            self.connected = True
            self._dispatch()

    @callback
    def _on_disconnected(self, client: BleakClient) -> None:
        self._client = None
        self.connected = False
        if self._closed:
            return
        self._dispatch()
        if self.keep_connected:
            self._schedule_connect()

    async def _async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except BLE_ERRORS:
                pass
        self.connected = False

    @callback
    def _on_notify(self, _char: object, data: bytearray) -> None:
        frame = bytes(data)
        status = parse_status(frame)
        if status is None:
            if is_protocol2_frame(frame) and not self.unsupported_protocol:
                self.unsupported_protocol = True
                _LOGGER.warning(
                    "%s speaks the newer TWD1 'protocol 2', which this integration "
                    "does not support (only 'protocol 1' desks work)",
                    self.name,
                )
            return
        changed = status != self.status
        self.status = status
        self.status_time = monotonic()
        if changed:
            self._dispatch()

    def _cancel_idle(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None

    def _touch(self) -> None:
        """Without keep-connected, close the link again after a quiet spell."""
        self._cancel_idle()
        if not self.keep_connected:
            self._idle_handle = self.hass.loop.call_later(
                IDLE_DISCONNECT_SECONDS,
                lambda: self.entry.async_create_background_task(
                    self.hass, self._async_disconnect(), f"{self.address} idle disconnect"
                ),
            )

    async def _async_write(self, frame: bytes) -> None:
        if self._client is None:
            raise HomeAssistantError("not connected")
        try:
            await self._client.write_gatt_char(WRITE_CHAR_UUID, frame, response=False)
        except BLE_ERRORS as err:
            raise HomeAssistantError(f"Bluetooth write failed: {err}") from err

    # -- commands ----------------------------------------------------------

    async def async_move_to(self, height_cm: int) -> None:
        """Drive to a height with the control box's own move-to-height command."""
        if not valid_height(height_cm):
            raise ServiceValidationError(
                f"Height must be between {HEIGHT_MIN_CM} and {HEIGHT_MAX_CM} cm"
            )
        await self._async_run(MoveKind.TARGET, move_to_frame(height_cm), height_cm)

    async def async_reset(self) -> None:
        """Run the control box's height reset (diagnostic; re-measures the lowest height)."""
        await self._async_run(MoveKind.RESET, RESET_FRAME, None)

    async def async_stop(self) -> None:
        """Stop a running move; also sends a stop frame when idle."""
        self._stop_requested.set()
        if self._move_lock.locked():
            return  # the running move sends the stop frames itself
        await self._async_connect()
        await self._async_write(STOP_FRAME)
        self._touch()

    async def _async_run(self, kind: MoveKind, frame: bytes, target: int | None) -> None:
        self._stop_requested.set()  # ask a previous move to wind down
        async with self._move_lock:
            self._stop_requested.clear()
            await self._async_connect()
            start = await self._async_first_status()
            supervisor = MoveSupervisor(kind, target_cm=target, start=start, now=monotonic())
            self.target_cm = target
            self._dispatch()
            abort: str | None = None
            try:
                while not self._stop_requested.is_set():
                    await self._async_write(frame)
                    await asyncio.sleep(SEND_INTERVAL)
                    now = monotonic()
                    decision = supervisor.update(self.status, now - self.status_time, now)
                    if decision.outcome is Outcome.DONE:
                        break
                    if decision.outcome is Outcome.ABORT:
                        abort = decision.reason
                        break
            finally:
                await self._async_send_stop()
                self.target_cm = None
                self._dispatch()
                self._touch()
            if abort:
                raise HomeAssistantError(f"Move stopped: {abort}")

    async def _async_first_status(self) -> DeskStatus:
        """A fresh status to start a move from.

        An idle desk goes quiet: it only streams while moving or after a frame
        from us. So if the last status is stale, ask for one (the stop frame is
        the "tell me your height" request) and wait for the reply.
        """
        deadline = monotonic() + FIRST_STATUS_TIMEOUT
        requested = False
        while monotonic() < deadline:
            if self.status is not None and monotonic() - self.status_time < 1.0:
                return self.status
            if not requested:
                requested = True
                await self._async_write(STOP_FRAME)
            await asyncio.sleep(0.1)
        if self.unsupported_protocol:
            raise HomeAssistantError(
                "This desk speaks the newer TWD1 'protocol 2', which this integration "
                "does not support (only 'protocol 1' desks work)"
            )
        raise HomeAssistantError("The desk is connected but not reporting its height")

    async def _async_send_stop(self) -> None:
        """Best effort: a failed stop must not hide the real error."""
        for _ in range(3):
            try:
                await self._async_write(STOP_FRAME)
            except HomeAssistantError:
                return
            await asyncio.sleep(SEND_INTERVAL)
