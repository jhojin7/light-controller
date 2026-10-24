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
C++ controller/renderer and test provisioning. Scenarios cover navigation,
button timing, request payloads, errors, OFF/back ON, configuration and layout.

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
```

`--skip-ha` skips HA connectivity checks explicitly. Live checks allow 20 seconds
for state convergence, brightness tolerance 3/255 and temperature tolerance 100 K.
Physical buttons, emitted display/light output and battery endurance need manual
checks; framebuffer verification does not measure those.

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

The tested light reports 2500 K after the configured SLEEP request of 2200 K,
including through a direct HA call. Strict live checks failed that temperature
comparison; the original light state was restored. These records do not represent
an all-green run of every live preset. Presets and tolerances remain unchanged.
