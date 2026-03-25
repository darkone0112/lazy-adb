from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

from core.device_info import DeviceInfo, detect_getprop_problem, parse_getprop_output
from core.device_state import (
    ConnectionMode,
    DeviceConnection,
    DeviceConnectionState,
    ListedDevice,
    parse_adb_devices_output,
    select_preferred_device,
)
from utils.platform_paths import get_bundled_adb_path


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.error_message is None

    def describe(self) -> str:
        if self.success:
            return "Command completed successfully."
        if self.timed_out:
            return "The command timed out before ADB responded."
        if self.error_message:
            return self.error_message
        if self.stderr.strip():
            return self.stderr.strip()
        return "ADB returned a non-zero exit code."


@dataclass(slots=True)
class DeviceDiscovery:
    command_result: CommandResult
    devices: list[ListedDevice]
    connection: DeviceConnection


@dataclass(slots=True)
class DeviceInfoResult:
    command_result: CommandResult
    device_info: DeviceInfo | None = None


class ADBManager:
    def __init__(self, adb_path: Path | None = None, default_timeout: float = 8.0) -> None:
        self._adb_path = adb_path
        self.default_timeout = default_timeout

    @property
    def adb_path(self) -> Path:
        if self._adb_path is None:
            self._adb_path = get_bundled_adb_path()
        return self._adb_path

    def build_command(self, args: list[str], *, serial: str | None = None) -> list[str]:
        command = [str(self.adb_path)]
        if serial:
            command.extend(["-s", serial])
        command.extend(args)
        return command

    def build_subprocess_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["creationflags"] = creationflags
            kwargs["startupinfo"] = startupinfo
        return kwargs

    def run(self, args: list[str], *, serial: str | None = None, timeout: float | None = None) -> CommandResult:
        command = self.build_command(args, serial=serial)

        if not self.adb_path.exists():
            return CommandResult(
                command=command,
                returncode=-1,
                error_message=(
                    f"Bundled ADB was not found at {self.adb_path}. "
                    "Place the platform-tools binary in the resources folder for this OS."
                ),
            )

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout or self.default_timeout,
                check=False,
                **self.build_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            return CommandResult(
                command=command,
                returncode=-1,
                stdout=stdout,
                stderr=stderr,
                error_message="ADB did not respond before the timeout expired.",
                timed_out=True,
            )
        except OSError as exc:
            return CommandResult(
                command=command,
                returncode=-1,
                error_message=f"Failed to launch ADB: {exc}",
            )

        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def get_version(self) -> CommandResult:
        return self.run(["version"])

    def clear_logcat(self, serial: str) -> CommandResult:
        return self.run(["logcat", "-c"], serial=serial, timeout=12.0)

    def pair_device(self, host: str, port: str, pairing_code: str) -> CommandResult:
        return self.run(["pair", f"{host}:{port}", pairing_code], timeout=20.0)

    def connect_device(self, host: str, port: str) -> CommandResult:
        return self.run(["connect", f"{host}:{port}"], timeout=20.0)

    def disconnect_device(self, target: str | None = None) -> CommandResult:
        args = ["disconnect"]
        if target:
            args.append(target)
        return self.run(args, timeout=20.0)

    def detect_devices(
        self,
        preferred_serial: str | None = None,
        mode: ConnectionMode = ConnectionMode.USB,
    ) -> DeviceDiscovery:
        result = self.run(["devices"])
        devices = parse_adb_devices_output(result.stdout)

        if not result.success and not devices:
            connection = DeviceConnection(
                state=DeviceConnectionState.ERROR,
                detail=result.describe(),
            )
        else:
            connection = select_preferred_device(
                devices,
                preferred_serial=preferred_serial,
                mode=mode,
            )

        return DeviceDiscovery(
            command_result=result,
            devices=devices,
            connection=connection,
        )

    def read_device_info(self, serial: str) -> DeviceInfoResult:
        result = self.run(["shell", "getprop"], serial=serial, timeout=12.0)
        if not result.success:
            return DeviceInfoResult(command_result=result)

        problem = detect_getprop_problem(result.stdout, result.stderr)
        if problem is not None:
            return DeviceInfoResult(
                command_result=CommandResult(
                    command=result.command,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error_message=problem,
                    timed_out=result.timed_out,
                )
            )

        device_info = parse_getprop_output(result.stdout, serial_number=serial)
        if not device_info.has_meaningful_properties():
            return DeviceInfoResult(
                command_result=CommandResult(
                    command=result.command,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error_message=(
                        "ADB reached the target, but the returned property set was too limited to identify "
                        "an Android device."
                    ),
                    timed_out=result.timed_out,
                )
            )

        return DeviceInfoResult(command_result=result, device_info=device_info)
