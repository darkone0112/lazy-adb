from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceConnectionState(str, Enum):
    NO_DEVICE = "no_device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    READY = "ready"
    ERROR = "error"


@dataclass(slots=True)
class ListedDevice:
    serial: str
    raw_state: str


@dataclass(slots=True)
class DeviceConnection:
    state: DeviceConnectionState
    serial: str | None = None
    raw_state: str | None = None
    detail: str | None = None


def parse_adb_devices_output(output: str) -> list[ListedDevice]:
    devices: list[ListedDevice] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        if line.startswith("*"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        devices.append(ListedDevice(serial=parts[0], raw_state=parts[1]))

    return devices


def normalize_device_state(raw_state: str) -> DeviceConnectionState:
    match raw_state:
        case "device":
            return DeviceConnectionState.READY
        case "unauthorized":
            return DeviceConnectionState.UNAUTHORIZED
        case "offline":
            return DeviceConnectionState.OFFLINE
        case _:
            return DeviceConnectionState.ERROR


def select_preferred_device(devices: list[ListedDevice]) -> DeviceConnection:
    if not devices:
        return DeviceConnection(
            state=DeviceConnectionState.NO_DEVICE,
            detail="No Android device is currently visible to ADB.",
        )

    priority_order = [
        DeviceConnectionState.READY,
        DeviceConnectionState.UNAUTHORIZED,
        DeviceConnectionState.OFFLINE,
        DeviceConnectionState.ERROR,
    ]

    for desired_state in priority_order:
        for device in devices:
            normalized = normalize_device_state(device.raw_state)
            if normalized is desired_state:
                return DeviceConnection(
                    state=normalized,
                    serial=device.serial,
                    raw_state=device.raw_state,
                )

    first = devices[0]
    return DeviceConnection(
        state=DeviceConnectionState.ERROR,
        serial=first.serial,
        raw_state=first.raw_state,
        detail=f"ADB reported an unsupported device state: {first.raw_state}.",
    )


def describe_connection_state(connection: DeviceConnection) -> tuple[str, str, str]:
    match connection.state:
        case DeviceConnectionState.NO_DEVICE:
            return (
                "Connect Your Device",
                "No device is ready yet. Follow the setup steps below before checking again.",
                "Connect the device by USB and confirm USB debugging is enabled.",
            )
        case DeviceConnectionState.UNAUTHORIZED:
            return (
                "Authorization Needed",
                "The device was found, but Android has not trusted this computer yet.",
                "Unlock the device and accept the USB debugging authorization prompt.",
            )
        case DeviceConnectionState.OFFLINE:
            return (
                "Connection Unstable",
                "The device is visible to ADB, but the connection is not stable enough yet.",
                "Reconnect the USB cable, keep the screen unlocked, and check the connection again.",
            )
        case DeviceConnectionState.READY:
            return (
                "Device Connected",
                "The device is ready. You can refresh the device information at any time.",
                "Review the detected details below and continue with the next support action.",
            )
        case DeviceConnectionState.ERROR:
            return (
                "ADB Needs Attention",
                connection.detail or "ADB returned a state the application does not understand yet.",
                "Check the status panel for the command result and confirm the bundled ADB files are present.",
            )

