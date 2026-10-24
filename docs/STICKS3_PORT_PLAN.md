# StickS3 port plan

Inspection date: 2026-10-24 (Asia/Seoul).

## Connection and baseline

- macOS exposes `/dev/cu.usbmodem101` and `/dev/tty.usbmodem101`.
- USB identifies as Espressif `USB JTAG_serial debug unit`, VID:PID
  `303a:1001`, USB serial `7C:E8:B1:E4:B2:98`.
- The serial port opened successfully at 115200 baud. A three-second passive
  read returned no output. USB data connectivity is confirmed; the descriptor
  alone does not establish the precise board model or installed firmware.
- No CIRCUITPY volume is mounted. No reset, bootloader command, erase, or
  firmware write was performed during inspection.
- PlatformIO, esptool, pyserial, and arduino-cli were not found in the checked
  Python environment/PATH. An isolated tool environment is needed.
- `make check` and `make test` pass (three host serial-transport tests).
  These do not establish that the application runs on the StickS3.
- The local configuration contains four modes and an entity ID. The four
  required Wi-Fi/HA settings are populated; values were not printed.
- Existing untracked `docs/DEMO_STORYBOARD.md` belongs to prior work.

## Recommended runtime

Add a separate `sticks3/` Arduino C++ target built with PlatformIO, using
M5Unified/M5GFX and the M5PM1 dependency required by the official configuration.
Keep the existing Feather firmware and deployment commands available.

The current application is CircuitPython and assumes `board.DISPLAY`,
`board.D1`, and `board.D2`; it cannot be copied directly onto this device.
Inspection of the current upstream CircuitPython ESP32 board directory found
no StickS3 target. Staying with CircuitPython would first require proving a
compatible generic build or adding board support, including display and power
initialization. That is a separate bring-up effort. Arduino is the recommended
route because M5Stack supplies StickS3 drivers and a PlatformIO configuration.

This recommendation entails translating the Python application to C++.
The mode data, glyph/icon data, layout, and behavior remain the specification.

## Hardware and behavior mapping

| Existing application | StickS3 implementation |
| --- | --- |
| 135 × 240 portrait display | ST7789P3, same logical resolution; verify rotation and panel offsets on hardware |
| `board.DISPLAY` / displayio | M5GFX drawing through M5Unified; use a sprite/canvas for complete frame updates |
| D1 cycles modes | BtnA on GPIO11 cycles modes |
| D2 applies selection | BtnB on GPIO12 applies selection |
| Active-high Feather inputs | M5Unified logical button state; do not copy the Feather pull-down configuration |
| Dotted headings and icons | Translate the existing bitmaps, colors, sizing, truncation, and placement |
| CircuitPython Wi-Fi and requests | Arduino Wi-Fi and HTTP clients, preserving HA requests and error behavior |
| `config.json` | Preserve the entity/mode JSON schema, including OFF and optional icons |
| `settings.toml` | Host deployment helper converts existing keys into device settings JSON |
| CircuitPython display initialization | M5Unified initializes the display and M5PM1 power management |

The reset/power button stays a system control. The display prompt must change
from `D2 TO APPLY` to match the StickS3 button labeling.

## Implementation sequence

1. **Prepare tools and recovery.** Install PlatformIO/esptool in an isolated
   environment. Re-discover the device rather than assume its port never changes.
   Probe chip and flash identity, enter download mode if necessary, and back up
   readable factory flash before the first erase/write. Keep any backup local
   and excluded from Git and distribution packages.
2. **Prove board bring-up.** Add `sticks3/platformio.ini` based on the official
   8 MB flash / octal PSRAM / native USB CDC example. Pin compatible dependency
   revisions after a successful build. Flash a small diagnostic app to verify
   portrait display, backlight, both buttons, serial logging, and power behavior
   on USB and battery. Avoid waiting indefinitely for a USB serial connection.
3. **Port the controller.** Implement mode loading/defaults, drawing, navigation,
   and applied-state tracking. Preserve DAY/EVENING/SLEEP/OFF, arbitrary mode
   counts, long-name handling, icon overrides, and error states. Preserve the
   current 300 ms input acceptance/held-repeat behavior and cycle-before-apply
   ordering unless deliberately changed later.
4. **Provision configuration and network.** Use LittleFS for `config.json` and
   generated device settings JSON. Add a host helper that reads existing local
   files, validates them, stages ignored device data, and uploads it. Keep secrets
   out of logs, source control, and distributable firmware/data packages. Use a
   compatible flash partition layout and avoid filesystem auto-format on failure.
   Verify 2.4 GHz Wi-Fi, HA hostname resolution, authentication, and the configured
   light with read-only API calls first. Preserve supported URL schemes with
   appropriate TLS validation when HTTPS is configured.
5. **Match HA behavior.** Send Bearer-authenticated POST requests to
   `/api/services/light/turn_on` with entity, brightness, and
   `color_temp_kelvin`; OFF sends only the entity to `light/turn_off`. Preserve
   the ten-second request timeout, success handling, and last successful mode
   on failure. Close network resources. Keep initialization and runtime failures
   visible on screen without printing credentials.
6. **Validate and document deployment.** Add StickS3 build/provision/upload/monitor
   commands and setup instructions. Adapt the behavior scenarios to the new
   runtime; the existing CircuitPython raw-REPL and displayio inspection suite
   cannot run unchanged against Arduino firmware.

## Completion criteria

- Cold boot and reset produce the correct 135 × 240 portrait UI without clipping.
- BtnA cycles through all configured modes and wraps; BtnB applies the selection.
- UI matches the existing reference screens, allowing for documented text-font
  differences if needed. Capture rendered framebuffer evidence where practical;
  physical orientation, backlight, and switch contacts need hardware checks.
- Missing/malformed configuration, empty modes, explicit icons, long names,
  missing credentials, and HTTP/network failures behave as specified.
- Read-only HA connectivity succeeds before live preset tests.
- Live validation snapshots the light, applies every configured preset including
  OFF and back ON, verifies results, and restores the original light state.
  The restoration must still run after a failed test when the connection permits.
- The device works without a connected serial monitor and after unplugging USB.
  Measure battery runtime later; do not assume continuous Wi-Fi/display use will
  provide long endurance from the built-in 250 mAh battery.
- Existing Feather checks still pass and its packaging excludes the new target's
  generated credentials and device backups.

## Sources

- [StickS3 hardware, pin map, power notes, download mode, and PlatformIO example](https://docs.m5stack.com/en/core/StickS3)
- [Official Arduino quick start](https://docs.m5stack.com/en/arduino/m5sticks3/program)
- [Official button example](https://docs.m5stack.com/en/arduino/m5sticks3/button)
- [Official display example](https://docs.m5stack.com/en/arduino/m5sticks3/display)
- [Current upstream CircuitPython ESP32 board targets](https://github.com/adafruit/circuitpython/tree/main/ports/espressif/boards)
- [M5Unified](https://github.com/m5stack/M5Unified), [M5GFX](https://github.com/m5stack/M5GFX), [M5PM1](https://github.com/m5stack/M5PM1)
