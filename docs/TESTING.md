# Testing and recovery

Use the commands for the target board. Hardware tests require its configured
Wi-Fi network and Home Assistant light. Close other serial monitors first.

## Local checks

| Target | Working directory | Commands |
| --- | --- | --- |
| Feather | Repository root, Python 3.9+ | `make check`, `make test`, `make package` |
| StickS3 | `sticks3/`, after `make setup` with Python 3.11+ | `make check`, `make build` |

Feather checks validate Python/configuration, exercise serial recovery against a
pseudo-terminal and package the application. StickS3 checks compile the actual
C++ controller/renderer and test provisioning. The mode/render harness covers
payloads, errors, OFF/back ON, configuration and layout. A separate fake-clock
interaction suite drives raw A/B levels through debounce, tap/hold, simultaneous
keys, wake release, deadlines, pending connection/apply, stale completion and
RTC retention recovery. The old StickS3 hold-repeat tests are superseded by
the new gesture contract; Feather timing is unchanged.

## Hardware checks

From the target's working directory:

```sh
make e2e                 # Board checks and read-only HA requests
make e2e-live            # Also change the light and restore its original state
```

The Feather runner loads `code.py` into RAM through the raw REPL, checks real
displayio output against bitmap goldens and runs deliberate regression controls.
It restarts the installed firmware afterward.

The StickS3 runner checks board identity, PSRAM, configuration, navigation and the
board framebuffer against the host renderer. Its serial commands call the
installed firmware. Both runners check HA authentication and entity access.

Useful options:

```sh
# Feather, from the repository root
python3 scripts/e2e.py --port /dev/cu.usbmodemYOUR_BOARD
python3 scripts/e2e.py --case off-and-back-on --skip-ha

# StickS3, from sticks3/
make e2e PORT=/dev/cu.usbmodemYOUR_BOARD
.venv/bin/python scripts/e2e.py --skip-ha --port /dev/cu.usbmodemYOUR_BOARD
.venv/bin/python scripts/e2e.py --sleep --port /dev/cu.usbmodemYOUR_BOARD
# With a person at the device, verify the exact physical wake pin:
.venv/bin/python scripts/wake_check.py --source b --port /dev/cu.usbmodemYOUR_BOARD
.venv/bin/python scripts/wake_check.py --source motion --port /dev/cu.usbmodemYOUR_BOARD
```

`--skip-ha` skips HA connectivity checks explicitly. Live checks allow 20 seconds
for state convergence, brightness tolerance 3/255 and temperature tolerance 100 K.
Physical buttons, emitted display/light output and battery endurance need manual
checks; framebuffer verification does not measure those.

Wake the StickS3 with motion/B before starting serial checks. The runner acquires
a bounded 120-second maintenance lease so the normal 3-second idle timeout cannot
interrupt checks. Normal status polling does not keep it awake. `--sleep` uses
a 2-second timer fallback, verifies the actual ESP deep-sleep wake cause and a
non-default retained selection, and releases its lease afterward. `wake_check.py`
allows 60 seconds for the physical gesture and checks GPIO12 for B or GPIO13 for
motion; a fallback timer wake fails the physical-source assertion. A wake key
held through boot must not immediately put the device back to sleep. Repeat
pickup, put-down, B sleep/wake and A hold/release on both USB and battery.
Use `--keep-awake` with `--sleep` to leave a bounded 120-second debugging lease
after recovery. Long live runs renew the lease before each preset. The runner
captures a lease before compiling the host renderer so compilation cannot use
up the 3-second wake window. Frame comparisons include the captured A-hold bar.

The main loop never runs HTTP synchronously. During a slow connection or apply,
verify that the hold indicator/status remains readable and B can request sleep.
An in-flight apply completes or times out before sleep; an unused wake cancels
background association after 3 seconds. Battery-side sleep current needs external
measurement equipment; USB charging percentage is not a sleep-current measurement.

## Live-test recovery

Live tests briefly change the configured light. Do not control that same light
from elsewhere during the run.

Both runners save its original state as a temporary HA scene. A `finally` block
restores the scene, verifies the state and deletes it, including after ordinary
failures, Ctrl-C or SIGTERM. Power/network loss or a second interruption can
prevent recovery.

If recovery fails, use the saved scene ID with HA's `scene.turn_on`. Verify the
light before deleting the scene with `scene.delete`.

| Target | Results and recovery information |
| --- | --- |
| Feather | `dist/e2e/<UTC timestamp>/report.json`, BMP screenshots; latest run pointer at `dist/e2e/latest.json` |
| StickS3 | Console results; frame at `.local/device-screen.png`; failed recovery record at `.local/live-recovery.json` |

These outputs are ignored by Git. StickS3 continues after a preset state mismatch
to check the remaining modes; Feather stops live presets at the first failure.

If serial commands time out, close other monitors, reset the board once and retry
a limited check. Normal controller operation does not need a serial monitor.

## Feather bitmap baselines

Goldens were rendered on CircuitPython 10.3.1. After an intentional UI change:

```sh
python3 scripts/e2e.py --skip-ha --update-goldens
# Inspect the generated BMPs before accepting them.
python3 scripts/e2e.py --skip-ha --prove-tests
```

Do not replace goldens to hide an unexplained rendering difference.

## Recorded verification

| Target | Recorded results |
| --- | --- |
| Feather, 2026-10-16 | 29 board/rendering/regression checks, 3 host transport tests and package checks passed; live DAY/EVENING passed |
| StickS3, 2026-10-24 | 27 C++ scenarios, 4 provisioning tests, build/upload, framebuffer and HA checks passed during bring-up; user confirmed physical controls and display |
| StickS3 backlight, 2026-10-24 | Hardware reported 20,000 Hz at brightness 128/255; user confirmed idle flicker was gone |
| StickS3 sleep/controls, 2026-10-24 | 22 mode/render scenarios, 50 interaction assertions, 4 provisioning checks, application/diagnostic builds and Feather checks passed. Final firmware upload, board identity/configuration, framebuffer equality, three consecutive read-only HA jobs and timer deep-sleep recovery with a non-default selection and command history passed. Physical motion wake recorded EXT1 GPIO13 (8192); B wake recorded EXT1 GPIO12 (4096) after wake-key/settling fixes. BMI270 power control read 0x04 (accelerometer only). Live DAY, EVENING, OFF and back ON passed; SLEEP retained the known 2200→2500 K mismatch. Original light state was restored and the temporary scene deleted. |

The physical B test initially reported no wake. Sleep settling now leaves B
armed, and RTC wake pins are released before sampling keys on boot. A short
10-second human-test fallback expired before a later B press; subsequent device
telemetry recorded the actual GPIO12 wake. The physical-source helper now uses
a 60-second fallback to allow time for the human step. Pickup sensitivity,
extended wake-cycle reliability and battery-side current still need broader
measurement. A flash backup was saved privately before the first feature upload.
During final validation, intermittent HA failures exposed incorrect socket
lifetime ordering: HTTPClient can still access its borrowed client in its
destructor after end(). Sockets now outlive HTTPClient and each job disables
connection reuse. The radio also remains fully awake during the brief awake
session; it is stopped for deep sleep. Three consecutive API/entity jobs and
live preset commands passed after these changes. Standby current and endurance
remain unmeasured.

The tested light reports 2500 K after the configured SLEEP request of 2200 K,
including through a direct HA call. Strict live checks failed that temperature
comparison in the new firmware run as well; the original light state was restored.
These records do not represent an all-green run of every live preset. Presets
and tolerances remain unchanged.
