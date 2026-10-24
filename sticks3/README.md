# Light Controller for M5Stack StickS3

An independent Arduino C++ implementation for the **StickS3 K150**, built with
PlatformIO. This target does not import, compile, or modify the CircuitPython
firmware at the repository root.

The 135 × 240 portrait UI retains the original dotted headings, icons, colors,
brightness/Kelvin values, page counter, and last successful command. **A**
(GPIO11, front button) cycles; **B** (GPIO12, side user button) applies. The
power/reset button retains its system function. Holding A or B repeats at the
original interval of more than 300 ms. If both are pressed, selection happens
before applying. Choose OFF and press B to turn the light off.

The top right shows battery percentage and a battery icon. A plus in the icon
indicates charging; a discharging battery at 20% or below turns red. Battery
readings refresh every 15 seconds, and Wi-Fi status sits immediately to their left.

![Four default mode cards](assets/ui-preview.png)

## Build and install

Requirements: Python **3.11+**, Git, Make, and a C++ compiler for host checks.
On macOS, install Apple's Command Line Tools if needed. USB must support data.

Run these commands **inside `sticks3/`**:

```sh
make setup
make check
make build

# Absolute paths may point to the original checkout's private settings.
make provision CONFIG=/path/to/config.json SETTINGS=/path/to/settings.toml

# Confirm the connected device before uploading. Port names can change.
.venv/bin/pio device list
make upload PORT=/dev/cu.usbmodem101
make upload-data PORT=/dev/cu.usbmodem101
.venv/bin/python scripts/e2e.py --port /dev/cu.usbmodem101
```

Firmware and filesystem upload are separate operations. Firmware updates leave
the settings partition intact; `upload-data` replaces that partition with the
contents of local `data/`. The firmware never automatically formats a failed
filesystem. With no settings, it shows an instruction/error and sends no HA
commands. Uploading either artifact restarts the device.

The environment pins Espressif32 6.12.0, Arduino ESP32 2.0.17, M5Unified 0.2.27,
M5GFX 0.2.34, and ArduinoJson 7.4.3. M5Unified includes its M5PM1 power driver;
no separate power library is required by this implementation. Audio, microphone,
IMU and RTC initialization are disabled because the controller does not use them.

The default PlatformIO LittleFS builder is an Intel binary even in its Apple
Silicon package. `make setup` builds the pinned upstream 3.2.0 tool natively in
`.local/`, with disk format 2.0 compatible with this Arduino runtime. A project
script selects that tool without changing global PlatformIO installations.
Uploads use `watchdog_reset`; the ordinary reset left the device without serial
output during bring-up. The upload baud is 115200 because macOS rejected a
custom-baud serial reconfiguration after the watchdog disconnected USB. No serial
monitor is needed for standalone startup.

For HTTPS, provision the trusted CA PEM as well:

```sh
make provision CONFIG=/path/to/config.json SETTINGS=/path/to/settings.toml CA=/path/to/ca.pem
```

HTTPS uses certificate verification and NTP to establish the clock. There is no
insecure fallback. Ensure the device can reach NTP, or use an appropriate trusted
local HTTP endpoint as in the original configuration.

## Configuration and privacy

`config.json` uses the same entity/modes schema as the Feather. The local
provisioner translates `CIRCUITPY_WIFI_SSID`, `CIRCUITPY_WIFI_PASSWORD`, `HA_URL`,
and `HA_TOKEN` from TOML to `data/settings.json`. It leaves the source files
unchanged. All generated data, build output, backups, and Python environments
are ignored by Git. Private settings files are created with mode 0600.

Device flash and filesystem images contain the settings in plaintext. Keep
`data/`, `.pio/`, and flash backups private. The source firmware image alone
contains no Wi-Fi password or HA token. Serial diagnostics do not export either.

Missing or malformed mode files use the built-in four-mode defaults. Structurally
invalid configurations show an ERROR card and cannot send requests. This is
stricter than the original implementation. Files are limited to 64 KiB each.
User-facing text uses the original uppercase alphabet; unsupported characters
appear as `?`. Small captions also use that alphabet, rather than CircuitPython's
terminal font. The default rotation is 0 (135 × 240); use 2 for the opposite
portrait orientation in both application and diagnostic setup if desired.

## Verification

```sh
make check
.venv/bin/python scripts/e2e.py --port /dev/cu.usbmodem101
# This command changes the actual light, then restores it:
.venv/bin/python scripts/e2e.py --port /dev/cu.usbmodem101 --live
```

Host checks compile the actual C++ controller and renderer. They cover navigation,
timing/held-repeat, simultaneous inputs, preset payloads, OFF/back ON, HTTP errors,
configuration errors, custom icons, text truncation, and the millis counter wrap.
Provisioning tests check conversion, private file permissions, HTTPS CA requirements,
and rejected settings preserving previous data.

Default E2E verifies board detection, PSRAM, portrait dimensions, configuration,
navigation/wrap, the board framebuffer against host execution, and read-only HA
authentication/entity access. `--skip-ha` explicitly skips HA. The captured frame
is `.local/device-screen.png`; it is the rendered image, not a photograph of the LCD.

`--live` first saves a temporary HA scene and a local recovery record, applies all
presets plus ON after OFF, verifies actual HA state, restores the original state,
then deletes the scene. Restoration runs in `finally`, including ordinary errors
and interrupts. If it fails, `.local/live-recovery.json` retains the recovery scene
and original state for manual recovery. Do not interrupt restoration a second time.

Manually verify physical A/B presses, display orientation/color/backlight, and
operation after unplugging USB. Serial navigation cannot verify switch contacts.
The built-in 250 mAh battery has limited endurance with continuous Wi-Fi and display;
battery runtime and sleep/wake behavior are not yet characterized.

On the connected light during bring-up, the SLEEP request of **2200 K** was
reported back as **2500 K**, both through this board and through a direct HA
request. Brightness 25 was reported as 26, within the test tolerance. The port
preserves the configured request. Strict live verification reports the Kelvin
mismatch and continues through OFF/back ON before restoring the original state.

Network requests are synchronous, with ten-second connection/read timeouts. They
temporarily block button handling. The Wi-Fi icon reflects the connection; it
does not guarantee HA authentication. Failed connections retry every 30 seconds.
The displayed applied mode remembers the
last successful controller command, rather than subscribing to external changes.

## Diagnostics and recovery

```sh
make diagnostic
.venv/bin/pio run -e diagnostic -t upload --upload-port /dev/cu.usbmodem101
make monitor PORT=/dev/cu.usbmodem101
```

The diagnostic prints board ID, display dimensions, PSRAM and battery every two
seconds, plus physical button events. It does not load credentials or use HA.
Re-upload the `sticks3` environment afterward to restore the app.

If upload cannot connect, follow [M5Stack's download-mode instructions](https://docs.m5stack.com/en/core/StickS3):
hold the side reset button until the internal green LED flashes, then retry.

The initial full-flash backup is kept under `.local/backups/` in the implementation
worktree. Restore the **matching device's** backup only when you intend to replace
the entire firmware and settings:

```sh
.venv/bin/python -m esptool --port /dev/cu.usbmodem101 --after watchdog-reset \
  write-flash 0 .local/backups/factory-7ce8b1e4b298.bin
```

## Layout

- `src/main.cpp`: hardware startup, LittleFS, Wi-Fi, HTTP and serial commands
- `src/controller.cpp`, `include/controller.h`: portable controller and HA payloads
- `src/screen.cpp`, `include/screen.h`, `include/bitmaps.h`: portable RGB565 renderer
- `src/diagnostic.cpp`: isolated hardware diagnostic environment
- `scripts/`: provisioning, native-tool setup, host checks and hardware E2E
- `tests/`: behavior traces, fixtures, C++ harness and provisioning tests

The newline-delimited serial JSON commands are `status`, `frame`, `next`, `apply`,
`ha_check`, and `wifi_scan`, e.g. `{"cmd":"status"}`. Status includes the last
disconnect reason and current RSSI; scans disclose only whether the configured
network is visible, rather than nearby SSIDs. An offline scan restarts association.
`apply` changes the real light. There
is no Python REPL or arbitrary code execution interface in this target.

The final USB diagnostic session timed out despite physical navigation continuing
to work. Serial diagnostics are not required for normal use; this remains a
development-tool limitation to investigate separately. Live DAY/EVENING and HA
connectivity were verified earlier; the strict SLEEP mismatch is documented above.

Hardware pinouts and the build baseline come from the [official StickS3 documentation](https://docs.m5stack.com/en/core/StickS3).
The original bitmap art and Light Controller logic retain the repository's MIT license.
