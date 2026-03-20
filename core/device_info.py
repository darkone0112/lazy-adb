from __future__ import annotations

from dataclasses import dataclass


UNKNOWN_VALUE = "Unknown"


@dataclass(slots=True)
class DeviceInfo:
    model: str = UNKNOWN_VALUE
    manufacturer: str = UNKNOWN_VALUE
    android_version: str = UNKNOWN_VALUE
    serial_number: str = UNKNOWN_VALUE
    build_id: str = UNKNOWN_VALUE
    fingerprint: str = UNKNOWN_VALUE
    device_name: str = UNKNOWN_VALUE

    def has_meaningful_properties(self) -> bool:
        return any(
            value != UNKNOWN_VALUE
            for value in [
                self.model,
                self.manufacturer,
                self.android_version,
                self.build_id,
                self.fingerprint,
                self.device_name,
            ]
        )


def parse_getprop_output(output: str, serial_number: str | None = None) -> DeviceInfo:
    properties: dict[str, str] = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("[") or "]: [" not in line:
            continue

        key_end = line.find("]: [")
        key = line[1:key_end]
        value = line[key_end + 4 : -1]
        properties[key] = value

    def value_for(*keys: str, default: str = UNKNOWN_VALUE) -> str:
        for key in keys:
            value = properties.get(key, "").strip()
            if value:
                return value
        return default

    return DeviceInfo(
        model=value_for("ro.product.model"),
        manufacturer=value_for("ro.product.manufacturer"),
        android_version=value_for("ro.build.version.release"),
        serial_number=serial_number or value_for("ro.serialno", "ro.boot.serialno"),
        build_id=value_for("ro.build.id"),
        fingerprint=value_for("ro.build.fingerprint"),
        device_name=value_for("ro.product.device", "ro.product.name"),
    )


def detect_getprop_problem(stdout: str, stderr: str = "") -> str | None:
    combined = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).lower()
    if "getprop: not found" in combined:
        return (
            "ADB reached the target, but `getprop` is not available there. "
            "This does not look like a standard Android device profile."
        )

    has_property_lines = any(
        line.strip().startswith("[") and "]: [" in line
        for line in stdout.splitlines()
    )
    if not has_property_lines:
        return (
            "ADB reached the target, but it did not return recognizable Android system properties. "
            "This target may not be supported by the MVP."
        )

    return None
