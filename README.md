# Lazy ADB Wizard

Lazy ADB Wizard is a PySide6 desktop application that helps support teams and testers collect Android diagnostics through ADB with a guided workflow. It supports both USB ADB and Wi-Fi ADB, can capture live `logcat`, export support packages, and includes a small advanced console for running direct ADB commands against the currently selected device.

The application is designed to work in two delivery models:

- source mode, where the tool is launched with Python from the repository
- portable packaged mode, where customers receive a folder containing `Lazy ADB Wizard.exe` and its runtime files

## What The Tool Does

The current MVP includes:

- USB ADB workflow with guided setup
- Wi-Fi ADB workflow with pairing and connect support
- automatic device detection and status refresh
- multi-device selection when more than one device is connected
- automatic first-run download of Google platform-tools when the current OS bundle is missing
- live `logcat` capture
- support package export as a `.zip`
- advanced ADB command window for the selected device
- fullscreen setup guides for USB and Wi-Fi
- optional session debug logging for the application itself

## Main Workflows

The application supports these main use cases:

1. A user connects an Android phone over USB, authorizes debugging, captures logs, and exports a support package.
2. A user pairs an Android phone over Wireless Debugging, connects over Wi-Fi, captures logs, and exports a support package.
3. A support engineer uses the Advanced window to run custom ADB commands on the selected device.
4. A customer receives a portable build and runs the app without installing Python manually.

## Requirements

### Runtime

- Python 3.11 or newer for source usage
- a supported OS:
  - Linux
  - Windows
  - macOS
- an Android device with Developer Options and debugging enabled

### Python Dependencies

The project currently depends on:

- `PySide6>=6.7,<7`
- `setuptools>=68`

These are listed in [requirements.txt](/home/javier/repos/lazy-adb/requirements.txt).

## Repository Layout

Important folders and files:

- [main.py](/home/javier/repos/lazy-adb/main.py): application entrypoint
- [core/](/home/javier/repos/lazy-adb/core): ADB logic, log capture, exporting, bootstrap logic
- [ui/](/home/javier/repos/lazy-adb/ui): Qt windows and widgets
- [utils/](/home/javier/repos/lazy-adb/utils): path helpers and file helpers
- [resources/platform-tools/](/home/javier/repos/lazy-adb/resources/platform-tools): bundled ADB location per OS
- [output/](/home/javier/repos/lazy-adb/output): captures and exported support packages
- [tests/](/home/javier/repos/lazy-adb/tests): unit tests
- [android-logo.ico](/home/javier/repos/lazy-adb/android-logo.ico): runtime application icon

## Running From Source

### 1. Create And Activate A Virtual Environment

On Linux or macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Start The Application

On Linux or macOS:

```bash
python3 main.py
```

Or, if you are inside the venv:

```bash
python main.py
```

On Windows:

```powershell
python main.py
```

## First Run Behavior And Platform-Tools

The app expects ADB in these locations:

- `resources/platform-tools/windows/adb.exe`
- `resources/platform-tools/linux/adb`
- `resources/platform-tools/darwin/adb`

If the platform-tools for the current OS are already present, the app uses them immediately.

If they are missing, the app automatically downloads the correct Google archive for the current OS on first start:

- Windows: `https://dl.google.com/android/repository/platform-tools-latest-windows.zip`
- Linux: `https://dl.google.com/android/repository/platform-tools-latest-linux.zip`
- macOS: `https://dl.google.com/android/repository/platform-tools-latest-darwin.zip`

This behavior is useful for GitHub-distributed builds where the platform-tools are intentionally not committed to the repository.

## USB ADB Workflow

Typical USB flow:

1. Launch the app.
2. Connect the Android device with a data-capable USB cable.
3. Unlock the device.
4. If Android shows `Allow USB debugging`, approve it.
5. Wait for the app to detect the device automatically.
6. If needed, click `Check Connection`.
7. Review device information in the main panel.
8. Click `Start Capture`.
9. Reproduce the issue on the phone.
10. Click `Stop Capture`.
11. Export the capture when needed.

### If USB Setup Has Never Been Done Before

The USB guide in the app covers this, but the short version is:

1. Open Android `Settings`.
2. Open `About phone`.
3. Tap `Build number` 7 times.
4. Go back and open `Developer Options`.
5. Enable `USB debugging`.
6. Restart the device.
7. Reconnect it and authorize the computer.

## Wi-Fi ADB Workflow

Typical Wi-Fi flow:

1. Switch the app to `Wi-Fi` mode.
2. If no wireless device is currently paired or connected, the wireless setup window opens automatically.
3. Fill in the device IP and ports.
4. Pair the device.
5. Connect the device.
6. Once connected, the device behaves like any other ready target in the app.
7. Capture and export logs the same way as in USB mode.

### Important Wi-Fi Terminology

The app uses two different ports because Wireless Debugging uses two different actions:

- `Connect Port`: shown on the main Android `Wireless debugging` screen next to the device IP
- `Pairing Port`: shown only after tapping `Pair device with pairing code`
- `Pairing Code`: also shown only inside `Pair device with pairing code`

The device IP stays the same, but the connect port and pairing port are different.

### Recommended Wi-Fi Entry Order

The guide is written around the simplest order:

1. Find the device IP.
2. Fill the `Connect Port` first, because Android shows it immediately on the main `Wireless debugging` screen.
3. Then open `Pair device with pairing code` on the phone.
4. Fill the `Pairing Port`.
5. Fill the `Pairing Code`.
6. Click `Pair Device`.
7. Click `Connect`.

### Enabling Wireless Debugging

If the device has never been prepared before:

1. Enable Developer Options by tapping `Build number` 7 times.
2. Open `Developer Options`.
3. Enable `USB debugging`.
4. Enable `Wireless debugging`.
5. Restart the device.
6. Return to `Developer Options` and confirm `Wireless debugging` is still enabled.

## Multi-Device Handling

When multiple Android devices are available, the app enables a device selector.

- In USB mode, the selector lets the user choose between detected USB devices.
- In Wi-Fi mode, wireless devices are handled separately from USB devices.
- The selected device is the target used for capture, export metadata, and Advanced commands.

## Capture And Live Feed

The live feed shows ongoing activity and `logcat` output.

General capture flow:

1. Connect or pair a device until it is ready.
2. Click `Start Capture`.
3. Use the Android device to reproduce the issue.
4. Watch the live feed for current activity and logs.
5. Click `Stop Capture`.

After capture stops:

- the app keeps the generated log file under `output/captures`
- the capture completion dialog offers immediate export of the latest log

## Exporting Support Packages

The application can export support packages as `.zip` archives.

Each export can include:

- metadata about the selected connection
- device information, when available
- the selected `logcat` capture

### Exporting The Latest Capture

When you stop a capture, the completion popup includes an `Export` option. That path exports the most recent capture directly and does not ask the user to choose a log first.

### Exporting A Different Saved Capture

The `Export Package` action in the top action bar is for exporting an existing saved capture, not only the latest one.

That flow is:

1. Click `Export Package`.
2. Choose a saved capture from the in-app export picker window.
3. Choose where the resulting `.zip` should be saved.

## Advanced Window

The `Advanced` button opens a terminal-like ADB command window for the currently selected device.

You enter only the ADB subcommand. The app supplies the selected device target automatically.

Examples:

```text
shell getprop
logcat -d
shell pm list packages
shell dumpsys battery
```

The output appears in the same terminal-style window.

## Output Structure

By default, the repository uses these output folders:

- [output/captures](/home/javier/repos/lazy-adb/output/captures): captured `logcat` sessions
- [output/exports](/home/javier/repos/lazy-adb/output/exports): exported support packages when an explicit destination is not chosen

In normal usage, the export flow asks the user where to save the final `.zip`.

## Hidden Application Debug Logging

The app includes an internal debug log intended to help investigate freezes or unexpected workflow behavior.

How to enable it:

1. Launch the app.
2. Triple-click the title at the top of the main window.
3. A popup confirms that debug logging is enabled for the current session.

Behavior:

- the log is written as `lazy-adb-debug.log`
- in source mode, it is written beside the project entrypoint
- in packaged mode, it is written beside the executable
- it resets to off when the app closes

This log is useful for tracking:

- background refresh cycles
- GUI update skips or applications
- ADB task starts and completions
- other workflow events that may help diagnose stalls

## Running Tests

Run all tests:

```bash
python -m unittest discover -s tests -v
```

You can also verify the source files compile:

```bash
python -m compileall main.py core ui utils tests
```

## Building A Portable Windows `.exe` With PyInstaller

The recommended packaging model for this project is a portable `onedir` build, not an installer.

That means the customer receives an extracted folder containing:

- `Lazy ADB Wizard.exe`
- bundled Qt runtime files
- `resources/`
- `output/`
- the runtime icon file

The customer then opens the `.exe` directly.

### Important Packaging Notes

- Build the Windows package on Windows.
- Do not try to create the Windows `.exe` from Linux or macOS.
- Use `onedir`, not `onefile`, for this project.
- Distribute the whole built folder as a zip, not just the `.exe`.

### Windows Build Steps

Open a terminal in the repository root on Windows:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Build the portable package:

```powershell
.\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name "Lazy ADB Wizard" --icon "lazy-adb-wizard.ico" --add-data "android-logo.ico;." --add-data "resources;resources" --add-data "output;output" main.py
```

### What Each Important Flag Does

- `--windowed`: prevents the app from opening as a console application
- `--onedir`: creates a portable folder instead of a single self-extracting executable
- `--icon "lazy-adb-wizard.ico"`: sets the Windows `.exe` icon
- `--add-data "android-logo.ico;."`: bundles the runtime icon file used by PySide6 for the open window icon
- `--add-data "resources;resources"`: bundles the application resources
- `--add-data "output;output"`: includes the output folder structure

### Where The Result Appears

The build output appears under:

```text
dist\Lazy ADB Wizard\
```

For delivery, zip the whole folder:

```powershell
Compress-Archive -Path ".\dist\Lazy ADB Wizard\*" -DestinationPath ".\dist\Lazy-ADB-Wizard-Windows.zip" -Force
```

The customer should:

1. extract the zip
2. open `Lazy ADB Wizard.exe`

### Including Platform-Tools In Customer Builds

You have two valid packaging models:

1. Include platform-tools inside `resources/platform-tools/windows/` before building.
   This is best for direct customer delivery when you want the app to work without downloading ADB on first run.
2. Leave platform-tools absent and let the first-run bootstrap download them automatically.
   This is useful for repository or GitHub distributions where heavy binaries are intentionally excluded.

## Converting A PNG Icon To ICO On Linux

If you want to generate the Windows `.ico` from Linux and already have a PNG source image, use ImageMagick:

```bash
magick 3874546-middle.png -background none -define icon:auto-resize=256,128,64,48,32,16 lazy-adb-wizard.ico
```

On systems with the older command name:

```bash
convert 3874546-middle.png -background none -define icon:auto-resize=256,128,64,48,32,16 lazy-adb-wizard.ico
```

To verify the result:

```bash
file lazy-adb-wizard.ico
```

## Troubleshooting

### The App Starts But No Device Is Detected

- confirm the device is unlocked
- confirm USB debugging or Wireless debugging is actually enabled
- confirm the ADB authorization prompt was accepted
- retry `Check Connection`
- use `Open Guide` for the full setup steps

### The App Downloads Platform-Tools On Every Start

- confirm the app has permission to write into its own `resources/platform-tools/<os>/` directory
- confirm the expected ADB executable exists after download

### The Packaged Windows App Opens Slowly

- make sure you built with `--onedir`
- run it from an extracted folder, not directly inside a zip
- avoid running it from a network path
- if necessary, test whether antivirus scanning of `adb.exe` is adding noticeable overhead

### The Window Icon Shows On Linux But Not On Windows

For Windows packaged builds, you need both:

- `--icon "lazy-adb-wizard.ico"` for the `.exe`
- `--add-data "android-logo.ico;."` so PySide6 can load the runtime window icon

## Current Version

Current project metadata in [pyproject.toml](/home/javier/repos/lazy-adb/pyproject.toml):

- package name: `lazy-adb`
- version: `0.1.0`

