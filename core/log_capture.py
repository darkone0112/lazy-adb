from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

from core.adb_manager import ADBManager, CommandResult
from utils.file_helpers import ensure_directory, get_captures_root, safe_name, utc_timestamp


@dataclass(slots=True)
class CaptureSession:
    serial: str
    log_path: Path
    started_at: datetime
    process: subprocess.Popen[str]


@dataclass(slots=True)
class CaptureStartResult:
    success: bool
    message: str
    session: CaptureSession | None = None
    clear_result: CommandResult | None = None


@dataclass(slots=True)
class CaptureStopResult:
    success: bool
    message: str
    log_path: Path | None = None
    stderr: str = ""


class LogCaptureManager:
    def __init__(self, adb_manager: ADBManager, captures_root: Path | None = None) -> None:
        self.adb_manager = adb_manager
        self.captures_root = captures_root or get_captures_root()
        self._active_session: CaptureSession | None = None
        self._active_log_handle = None

    @property
    def active_session(self) -> CaptureSession | None:
        return self._active_session

    def start_capture(self, serial: str, *, clear_existing_logs: bool = True) -> CaptureStartResult:
        if self._active_session is not None:
            return CaptureStartResult(
                success=False,
                message="A log capture is already running. Stop it before starting another one.",
            )

        clear_result: CommandResult | None = None
        if clear_existing_logs:
            clear_result = self.adb_manager.clear_logcat(serial)
            if not clear_result.success:
                return CaptureStartResult(
                    success=False,
                    message=f"Could not clear the device log buffer before capture: {clear_result.describe()}",
                    clear_result=clear_result,
                )

        session_dir = ensure_directory(self.captures_root / f"{utc_timestamp()}_{safe_name(serial)}")
        log_path = session_dir / "logcat.txt"
        log_handle = log_path.open("w", encoding="utf-8")

        try:
            process = subprocess.Popen(
                self.adb_manager.build_command(["logcat"], serial=serial),
                stdout=log_handle,
                stderr=subprocess.PIPE,
                text=True,
                **self.adb_manager.build_subprocess_kwargs(),
            )
        except OSError as exc:
            log_handle.close()
            return CaptureStartResult(
                success=False,
                message=f"Could not start log capture: {exc}",
                clear_result=clear_result,
            )

        time.sleep(0.1)
        if process.poll() is not None:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read() or ""
            log_handle.close()
            return CaptureStartResult(
                success=False,
                message="ADB exited immediately when log capture started." + (f" {stderr.strip()}" if stderr.strip() else ""),
                clear_result=clear_result,
            )

        session = CaptureSession(
            serial=serial,
            log_path=log_path,
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._active_session = session
        self._active_log_handle = log_handle

        return CaptureStartResult(
            success=True,
            message=f"Log capture started for {serial}.",
            session=session,
            clear_result=clear_result,
        )

    def stop_capture(self) -> CaptureStopResult:
        session = self._active_session
        if session is None:
            return CaptureStopResult(
                success=False,
                message="No active log capture is currently running.",
            )

        process = session.process
        stderr_output = ""

        if process.poll() is None:
            process.terminate()
            try:
                _, stderr_output = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr_output = process.communicate(timeout=5)
        elif process.stderr is not None:
            stderr_output = process.stderr.read() or ""

        if self._active_log_handle is not None:
            self._active_log_handle.close()

        self._active_log_handle = None
        self._active_session = None

        if process.returncode not in (0, -15, 143):
            return CaptureStopResult(
                success=False,
                message="The capture process stopped unexpectedly.",
                log_path=session.log_path,
                stderr=stderr_output,
            )

        return CaptureStopResult(
            success=True,
            message=f"Log capture stopped. File saved to {session.log_path}.",
            log_path=session.log_path,
            stderr=stderr_output,
        )
