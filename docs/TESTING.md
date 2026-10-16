# Repeatable end-to-end verification

## Commands

Use Python 3.9+ on macOS or Linux. No third-party host packages are required.
The board needs its normal CircuitPython libraries, valid Wi-Fi/HA settings, and
its real light entity in `CIRCUITPY/config.json`.

```sh
make check                 # Syntax and configuration validation
make test                  # Host serial integration tests; no board needed
make e2e                   # Board scenarios + real HA GET checks, no light writes
make e2e-live              # Also apply every real preset and restore the light
```

`e2e-live` briefly changes the configured light, including OFF when configured,
then turns it back on, restores its original state, and verifies the restoration.
Avoid editing settings or using the same light concurrently during that run.

For a specific serial device or a limited run:

```sh
python3 scripts/e2e.py --port /dev/cu.usbmodemYOUR_BOARD
python3 scripts/e2e.py --case off-and-back-on --skip-ha
python3 scripts/e2e.py --skip-ha --prove-tests
```

The runner fails rather than silently skipping a missing board, failed HA check,
or missing bitmap baseline. `--skip-ha` is an explicit simulated-network-only
run on the real board; it is not a substitute for the live run.

## What executes

The host sends the repository's complete `code.py` into the board's raw REPL in
RAM. The application has an import-safe `run()` entry point; the tests call that
same entry point and execute its actual startup and event loop. They do not copy
or extract the loop, stub application functions, or replace the display library.
Installed firmware, credentials and configuration are not overwritten by tests.
At exit the runner restarts the installed firmware.

1. **Board contract scenarios:** use real `displayio`, `terminalio`, labels,
   dotted glyphs and icons. External configuration files, Wi-Fi, HTTP, time and
   button input levels are adapted. Cases cover navigation, debounce, success,
   failures, variable mode counts, fallback configurations, OFF and back on.
2. **Rendered output:** check text bounds and overlap on every input frame.
   Composite real TileGrid/font pixels into BMP screenshots. Compare five
   deterministic screens against reviewed goldens: DAY, EVENING, SLEEP, OFF,
   and an explicit icon override. The legacy three-mode fixture intentionally
   remains covered independently of the four-mode default.
3. **Negative controls:** deliberately change only the in-memory firmware copy
   to introduce known regressions, and require the corresponding tests to fail.
   Disk files and installed firmware are untouched.
4. **Real HA checks:** actual ESP32 Wi-Fi, authentication, configured entity
   availability, color-temperature capability and supported preset ranges.
5. **Optional live control:** actual firmware D1/D2 paths, actual requests, and
   HA state polling after each preset. Button levels/time are scripted; network,
   display and HA are real. A test never treats HTTP success alone as proof that
   the requested state was reached.

Defaults are 20 seconds for HA state convergence, brightness tolerance 3/255,
Kelvin tolerance 100 K, and small color-component tolerances when restoring.
These account for integration quantization; expected and observed values are
recorded so tolerance cannot conceal a completely different mode.

## Reports and visual review

Each run creates `dist/e2e/<UTC timestamp>/report.json` and BMP screenshots.
`dist/e2e/latest.json` points to the latest result data. Reports include the tested
source SHA-256, timestamps, hardware metadata, per-case results, live expected
and observed states, and recovery outcome. Outputs are ignored by Git. They do
not include tokens, Wi-Fi passwords or arbitrary serial tracebacks.

A full passing run requires every requested case, every golden comparison and
live restoration to pass. A partial run or `--skip-ha` is labeled accordingly.
Read the `live` and `ha_skipped` fields before claiming live verification.

Baseline screenshots were rendered on CircuitPython 10.3.1. A built-in font or
rendering change in another firmware version may require deliberate review.

To update baselines after an intentional UI change:

```sh
python3 scripts/e2e.py --skip-ha --update-goldens
# Open the resulting screenshots and inspect every changed screen.
python3 scripts/e2e.py --skip-ha --prove-tests
```

Do not use `--update-goldens` to make an unexplained difference disappear.
Golden updates are explicit; ordinary runs never rewrite them.

## Recovery and interruptions

The live suite creates a uniquely named temporary HA scene containing the
original light state before changing it. In a `finally` block it activates that
snapshot, polls until restoration is confirmed, then deletes the scene. If a
live request fails, the remaining presets stop and recovery still runs. Ctrl-C
and SIGTERM also enter that recovery path. Serial timeouts are bounded; the
runner attempts to cancel a pending probe before sending recovery commands.

If USB/power/network disappears, automated recovery cannot be guaranteed. A
failed cleanup leaves the snapshot ID in the report and console, for example
`scene.light_controller_e2e_<id>`. Restore it from HA with `scene.turn_on`, verify
the light, then remove it with `scene.delete`. Keep the snapshot until verified.
The scene actions follow the [Home Assistant scene documentation](https://www.home-assistant.io/integrations/scene/).

Close other serial monitors first. If the board stops responding, press Reset
once and retry a single scenario before the full suite. Image data is compressed
and captured one screen per request to avoid large transfers on the board.

## Physical checks still required

Software E2E does not actuate physical switch contacts or inspect emitted light.
For a final hardware acceptance check, press D1 through all four modes, press D2
on OFF and on an on preset, and confirm the physical TFT and lamp match HA.
The suite also does not simulate power loss or prove long-term Wi-Fi recovery.

## Verification recorded on 2026-10-16

On CircuitPython 10.3.1, all 29 board contract, rendered-screen and deliberate
regression checks passed. The three host serial integration tests and deployment
package checks also passed. Real HA authentication and DAY/EVENING state checks
passed. The strict SLEEP state check reported 2500 K after requesting 2200 K
(brightness 26 versus requested 25, within the brightness tolerance). It failed
the Kelvin tolerance; the suite did not continue to the live OFF/back-on cases.
The original light state was restored and the temporary scene deleted.

The user subsequently confirmed that all four physical modes work and requested
that testing stop. Presets and tolerances were left unchanged. Live automated
coverage is therefore partial, not an all-green full live run. The complete
machine-readable run remains locally under
`dist/e2e/20261016T035224056351Z/report.json` (ignored by Git).
