from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceConnectionState(str, Enum):
    NO_DEVICE = "no_device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    READY = "ready"
    ERROR = "error"


class ConnectionMode(str, Enum):
    USB = "usb"
    WIFI = "wifi"


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


def is_wireless_serial(serial: str) -> bool:
    lowered = serial.lower()
    if "._adb-tls-connect._tcp" in lowered or "._adb-tls-pairing._tcp" in lowered:
        return True
    if lowered.startswith("adb-") and "._adb-tls-" in lowered:
        return True
    if ":" not in serial:
        return False

    host, port = serial.rsplit(":", 1)
    return bool(host and port.isdigit())


def filter_devices_for_mode(devices: list[ListedDevice], mode: ConnectionMode) -> list[ListedDevice]:
    if mode is ConnectionMode.WIFI:
        return [device for device in devices if is_wireless_serial(device.serial)]
    return [device for device in devices if not is_wireless_serial(device.serial)]


def select_preferred_device(
    devices: list[ListedDevice],
    preferred_serial: str | None = None,
    mode: ConnectionMode = ConnectionMode.USB,
) -> DeviceConnection:
    visible_devices = filter_devices_for_mode(devices, mode)

    if not visible_devices:
        return DeviceConnection(
            state=DeviceConnectionState.NO_DEVICE,
            detail=(
                "No wireless Android device is currently visible to ADB."
                if mode is ConnectionMode.WIFI
                else "No Android device is currently visible to ADB."
            ),
        )

    if preferred_serial:
        selected = next((device for device in visible_devices if device.serial == preferred_serial), None)
        if selected is not None:
            normalized = normalize_device_state(selected.raw_state)
            if normalized is DeviceConnectionState.ERROR:
                return DeviceConnection(
                    state=DeviceConnectionState.ERROR,
                    serial=selected.serial,
                    raw_state=selected.raw_state,
                    detail=f"ADB reported an unsupported device state: {selected.raw_state}.",
                )
            return DeviceConnection(
                state=normalized,
                serial=selected.serial,
                raw_state=selected.raw_state,
            )

    priority_order = [
        DeviceConnectionState.READY,
        DeviceConnectionState.UNAUTHORIZED,
        DeviceConnectionState.OFFLINE,
        DeviceConnectionState.ERROR,
    ]

    for desired_state in priority_order:
        for device in visible_devices:
            normalized = normalize_device_state(device.raw_state)
            if normalized is desired_state:
                return DeviceConnection(
                    state=normalized,
                    serial=device.serial,
                    raw_state=device.raw_state,
                )

    first = visible_devices[0]
    return DeviceConnection(
        state=DeviceConnectionState.ERROR,
        serial=first.serial,
        raw_state=first.raw_state,
        detail=f"ADB reported an unsupported device state: {first.raw_state}.",
    )


def describe_connection_state(
    connection: DeviceConnection,
    mode: ConnectionMode = ConnectionMode.USB,
) -> tuple[str, str, str]:
    match connection.state:
        case DeviceConnectionState.NO_DEVICE:
            if mode is ConnectionMode.WIFI:
                return (
                    "Wireless ADB Setup",
                    "No wireless device is connected yet. Pair and connect from the fields below.",
                    "Open Wireless debugging on the device, then enter the host, ports, and pairing code.",
                )
            return (
                "Connect Your Device",
                "No device is ready yet. Follow the setup steps below before checking again.",
                "Connect the device by USB and confirm USB debugging is enabled.",
            )
        case DeviceConnectionState.UNAUTHORIZED:
            if mode is ConnectionMode.WIFI:
                return (
                    "Wireless Authorization Needed",
                    "The wireless target was found, but Android has not trusted this computer yet.",
                    "Check the device for a wireless debugging authorization prompt and accept it.",
                )
            return (
                "Authorization Needed",
                "The device was found, but Android has not trusted this computer yet.",
                "Unlock the device and accept the USB debugging authorization prompt.",
            )
        case DeviceConnectionState.OFFLINE:
            if mode is ConnectionMode.WIFI:
                return (
                    "Wireless Connection Unstable",
                    "The wireless target is visible to ADB, but the connection is not stable yet.",
                    "Reconnect to the device IP and port shown in Wireless debugging, then try again.",
                )
            return (
                "Connection Unstable",
                "The device is visible to ADB, but the connection is not stable enough yet.",
                "Reconnect the USB cable, keep the screen unlocked, and check the connection again.",
            )
        case DeviceConnectionState.READY:
            if mode is ConnectionMode.WIFI:
                return (
                    "Wireless Device Connected",
                    "The wireless target is ready. You can refresh device information or start capture.",
                    "Review the connected target below and continue with the next support action.",
                )
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
