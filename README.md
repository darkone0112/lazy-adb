# Lazy ADB Wizard

Lazy ADB Wizard is a desktop tool for collecting Android diagnostics through ADB without making people live in a terminal all day. It supports USB ADB, Wi-Fi ADB, live `logcat` capture, support-package export, and a built-in advanced console for when you still want to type commands manually because apparently suffering is part of the workflow.

This README covers:

- what the tool does
- how to run it from source
- how to use the USB and Wi-Fi flows
- how capture and export work
- how to build the Windows `.exe` with PyInstaller

It does not try to be a startup pitch deck. Just the useful stuff.

## Features

- USB ADB workflow with guided setup
- Wi-Fi ADB workflow with Android Wireless Debugging
- automatic device detection and status refresh
- multi-device selection when more than one target exists
- automatic first-run download of Google platform-tools when the bundled ADB for the current OS is missing
- live `logcat` capture
- export of support packages as `.zip`
- advanced ADB command window for the selected device
- fullscreen USB and Wi-Fi setup guides
- optional internal debug logging for the app itself

## Requirements

### Runtime

- Python `3.11+` if you run from source
- one of these operating systems:
  - Linux
  - Windows
  - macOS
- an Android device with Developer Options and debugging enabled

### Python Dependencies

Current dependencies are listed in [requirements.txt](/home/javier/repos/lazy-adb/requirements.txt):

- `PySide6>=6.7,<7`
- `setuptools>=68`

## Repository Layout

Important paths:

- [main.py](/home/javier/repos/lazy-adb/main.py): app entrypoint
- [core/](/home/javier/repos/lazy-adb/core): ADB logic, capture, export, bootstrap
- [ui/](/home/javier/repos/lazy-adb/ui): Qt windows and widgets
- [utils/](/home/javier/repos/lazy-adb/utils): path and file helpers
- [resources/platform-tools/](/home/javier/repos/lazy-adb/resources/platform-tools): bundled ADB location per OS
- [output/](/home/javier/repos/lazy-adb/output): captures and exported packages
- [tests/](/home/javier/repos/lazy-adb/tests): tests

## Running From Source

### 1. Create And Activate A Virtual Environment

Linux or macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Start The App

Linux or macOS:

```bash
python3 main.py
```

If the venv is active, this works too:

```bash
python main.py
```

Windows:

```powershell
python main.py
```

## Platform-Tools Behavior

The app expects ADB in these locations:

- `resources/platform-tools/windows/adb.exe`
- `resources/platform-tools/linux/adb`
- `resources/platform-tools/darwin/adb`

If the matching ADB binary for the current OS is already there, the app uses it.

If it is missing, the app downloads Google platform-tools on first start:

- Windows: `https://dl.google.com/android/repository/platform-tools-latest-windows.zip`
- Linux: `https://dl.google.com/android/repository/platform-tools-latest-linux.zip`
- macOS: `https://dl.google.com/android/repository/platform-tools-latest-darwin.zip`

So yes, the repo can stay lighter and the app can still fix itself on first launch. For once, something behaves.

## USB Workflow

Normal USB flow:

1. Launch the app.
2. Connect the phone with a data-capable USB cable.
3. Unlock the phone.
4. Accept the `Allow USB debugging` prompt if Android shows it.
5. Let the app detect the device automatically.
6. If needed, click `Check Connection`.
7. Review the device information.
8. Click `Start Capture`.
9. Reproduce the issue.
10. Click `Stop Capture`.
11. Export the support package if needed.

### If USB Debugging Was Never Enabled Before

1. Open Android `Settings`.
2. Open `About phone`.
3. Tap `Build number` 7 times.
4. Go back and open `Developer Options`.
5. Enable `USB debugging`.
6. Restart the device.
7. Reconnect it and approve the computer.

## Wi-Fi Workflow

Normal Wi-Fi flow:

1. Switch the app to `Wi-Fi`.
2. If no wireless device is detected after the app checks, the setup window opens.
3. Fill `Host / IP`.
4. Fill `Connect Port`.
5. If this is a new pairing, also fill `Pair Port` and `Pairing Code`.
6. Click `Connect Device`.
7. The app will:
   - pair and then connect if the pairing fields are filled
   - connect only if the pairing fields are left empty
8. Once connected, use the device exactly like a USB-connected target.

### The Two Ports Android Shows

Wireless Debugging uses two different ports:

- `Connect Port`
  - shown on the main `Wireless debugging` screen next to the device IP
- `Pairing Port`
  - shown only after tapping `Pair device with pairing code`
- `Pairing Code`
  - shown in that same pairing screen

The IP usually stays the same.
The pairing port and connect port are different.
Because Android enjoys making simple things look suspicious.

### Recommended Wi-Fi Entry Order

1. Open `Wireless debugging` on the phone.
2. Copy the device IP.
3. Copy the `Connect Port` first, because it is visible immediately.
4. Tap `Pair device with pairing code`.
5. Copy the `Pairing Port`.
6. Copy the `Pairing Code`.
7. Fill the app and click `Connect Device`.

### If Wireless Debugging Was Never Enabled Before

1. Enable Developer Options by tapping `Build number` 7 times.
2. Open `Developer Options`.
3. Enable `USB debugging`.
4. Enable `Wireless debugging`.
5. Restart the phone.
6. Go back and confirm `Wireless debugging` is still enabled.

### About Disconnect / Forget

`Disconnect / Forget` disconnects the active wireless ADB session.

It does not erase the pairing stored on the Android device. That part still has to be removed on the phone from the Wireless Debugging paired devices/computers list. The app shows that reminder on purpose, because pretending otherwise would be nonsense.

## Multi-Device Behavior

When more than one device is available:

- USB mode shows a selector for USB devices
- Wi-Fi mode shows a selector for Wi-Fi targets
- the selected device is the target used for capture, export metadata, and Advanced commands

USB and Wi-Fi targets are intentionally separated so the app does not mash them together into one confusing list.

## Capture And Live Feed

The live feed shows app activity and streamed `logcat` output.

Basic flow:

1. Connect a ready device.
2. Click `Start Capture`.
3. Reproduce the issue.
4. Watch the feed if useful.
5. Click `Stop Capture`.

After capture stops:

- the log stays under `output/captures`
- the stop-capture popup offers immediate export of the latest log

## Exporting Logs

Support packages are exported as `.zip` archives.

They can contain:

- connection metadata
- device information if available
- the selected `logcat` capture

### Export The Latest Capture

After stopping capture, use the `Export` button in the completion popup. That uses the latest captured log directly.

### Export An Older Capture

Use `Export Package` from the top bar:

1. click `Export Package`
2. choose one of the saved captures from the in-app picker
3. choose where to save the resulting `.zip`

## Advanced Window

The `Advanced` button opens a terminal-style ADB window for the current device.

You only type the ADB subcommand. The app adds the selected device automatically.

Examples:

```text
shell getprop
logcat -d
shell pm list packages
shell dumpsys battery
```

Output appears in that same window.

## Output Structure

Relevant folders:

- [output/captures](/home/javier/repos/lazy-adb/output/captures): saved `logcat` sessions
- [output/exports](/home/javier/repos/lazy-adb/output/exports): exported packages when no explicit destination is used

In the normal UI flow, export asks where to save the final `.zip`.

## Hidden Debug Logging

The app has an internal debug log to help diagnose freezes or weird UI behavior.

How to enable it:

1. launch the app
2. triple-click the title at the top
3. the app shows a popup confirming the log is enabled for this session

Behavior:

- the file is named `lazy-adb-debug.log`
- in source mode it is written beside the project
- in packaged mode it is written beside the executable
- it turns off again when the app closes

This log tracks things like:

- background refresh cycles
- GUI update decisions
- ADB task start/finish events
- state transitions

Useful when the app decides to become dramatic.

## Running Tests

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Quick compile check:

```bash
python -m compileall main.py core ui utils tests
```

## Building The Windows `.exe` With PyInstaller

This project is meant to be packaged as a portable `onedir` build.

That means:

- no installer
- no `onefile`
- just a folder with the `.exe` and the runtime files it needs

### Important Notes

- Build the Windows `.exe` on Windows.
- Do not try to build the Windows `.exe` from Linux or macOS.
- Use `onedir`, not `onefile`.
- Zip the whole output folder, not just the `.exe`.

### Windows Build Steps

In the repo root on Windows:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Run this exact command to build the portable `.exe` folder:

```powershell
.\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name "Lazy ADB Wizard" --icon "lazy-adb-wizard.ico" --add-data "android-logo.ico;." --add-data "resources;resources" --add-data "output;output" main.py
```

### What The Important Flags Do

- `--windowed`
  - prevents a console window from opening with the app
- `--onedir`
  - creates a portable folder instead of one big self-extracting blob
- `--add-data "resources;resources"`
  - bundles the app resources
- `--add-data "output;output"`
  - keeps the expected output folder structure

### Result

The build appears here:

```text
dist\Lazy ADB Wizard\
```

Zip that whole folder for delivery:

```powershell
Compress-Archive -Path ".\dist\Lazy ADB Wizard\*" -DestinationPath ".\dist\Lazy-ADB-Wizard-Windows.zip" -Force
```

Then the other person:

1. extracts the zip
2. opens `Lazy ADB Wizard.exe`

### Include Platform-Tools Or Not

You have two sane options:

1. Put Windows platform-tools into `resources/platform-tools/windows/` before building.
   Best when you want the app to work immediately with no first-run download.
2. Leave platform-tools out and let the app download them on first run.
   Best when you want the repo and package lighter.

## Troubleshooting

### No Device Is Detected

- make sure the phone is unlocked
- make sure USB or Wireless Debugging is actually enabled
- accept the authorization prompt on the phone
- click `Check Connection`
- use `Open Guide` if the setup still fights back

### Platform-Tools Download Every Time

- check that the app can write into `resources/platform-tools/<os>/`
- check that the expected ADB executable really exists after download
