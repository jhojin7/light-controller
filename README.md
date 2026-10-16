# Light Controller

A physical Home Assistant light controller for the **Adafruit ESP32-S3 Reverse
TFT Feather (5691)**, running CircuitPython.

The portrait UI displays one mode at a time: a large dotted bitmap title,
sun/sunset/moon/power icon, brightness, Kelvin, and a `1/n` position indicator.
**D1** cycles through all configured modes; **D2** applies the displayed mode.
`ON:` shows the last successfully applied on-mode; `LIGHT OFF` confirms a
successful OFF request. The Wi-Fi icon turns green
when connected. The font and icons are built into the firmware.

![Controller UI](assets/ui-preview.png)

## Project layout

```text
code.py                CircuitPython application
boot.py                Suppress the display's boot/REPL console
config.json.example    Distributable light entity and four-mode template
config.json            Local deployment settings
settings.toml.example  Wi-Fi and Home Assistant settings template
docs/SETUP_GUIDE.md     Board setup and library installation
docs/FEATURE_MAP.md     Features, behavior, limitations and test coverage
docs/TESTING.md         Repeatable hardware/HA test commands and recovery
assets/ui-preview.png  Preview of the three default modes
scripts/check.py       Host-side syntax and configuration checks
scripts/package.py     Create a board-ready application ZIP
scripts/e2e.py         On-board E2E runner and optional real light control
tests/                 Input traces, board adapters, transport tests and goldens
```

This is firmware, so `code.py` and `boot.py` remain at the project root to
match the CIRCUITPY drive layout. The application runs on the Feather;
the development scripts run on a computer with Python 3.9 or newer.

## Board setup

1. Install CircuitPython and the matching Adafruit libraries using the
   [setup guide](docs/SETUP_GUIDE.md).
2. Copy `code.py` and `boot.py` to the CIRCUITPY root. Copy
   `config.json.example` there as `config.json` (or use your local config).
3. Copy `settings.toml.example` to the board as `settings.toml`, then enter
   your Wi-Fi credentials, Home Assistant URL, and long-lived access token.
4. Set your light's entity ID and desired modes in the board's `config.json`.
5. Reset the board. D1 cycles; D2 applies.

The board needs `adafruit_display_text`, `adafruit_requests`, and
`adafruit_connection_manager` in `CIRCUITPY/lib`. These libraries and
CircuitPython itself are installed separately and are not included in the ZIP.

## Development and packaging

```sh
make check
make package
make test
make e2e
```

Or run the scripts directly:

```sh
python3 scripts/check.py
python3 scripts/package.py
```

Checks parse the Python files and validate the distributable modes and settings
template without importing CircuitPython hardware modules. `make test` verifies
serial recovery against a pseudo-terminal. `make e2e` executes the full firmware
on the connected board, compares rendered screens, injects logical button inputs
and checks the real HA API without changing the light. `make e2e-live` additionally
applies all four presets and restores the original light state. See the
[feature map](docs/FEATURE_MAP.md) and [testing guide](docs/TESTING.md).

Packaging produces `dist/light-controller.zip`, containing the firmware,
configuration and settings templates, license, README, and setup guide.
It always uses an explicit file list and the `config.json.example` template,
excluding local configuration and credentials.
No Python packages are needed for either development command.

## Modes and orientation

Each mode has a `name`, `brightness` (0–255), and positive `kelvin` value.
The list can contain any nonzero number of modes. An optional `icon` value
(`sun`, `sunset`, `moon`, or `off`) overrides automatic icon selection for on
presets. An OFF entry needs only `{"name": "OFF", "action": "off"}`; it sends
`light.turn_off` with the entity ID and no color/brightness fields. D1 cycles
back from OFF to DAY; D2 applies either action.

Portrait rotation is `90` degrees in `code.py`; use `270` if mounting the
board in the opposite orientation. Long names are shortened on screen.

The default `config.json.example` is a template. `settings.toml` is ignored by Git;
keep your credentials in that local file or directly on the board.

## License

[MIT](LICENSE), matching the existing firmware license headers.
