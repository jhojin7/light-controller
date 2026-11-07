# Feather setup

For the **Adafruit ESP32-S3 Reverse TFT Feather (5691)**. For M5Stack hardware,
use the [StickS3 guide](https://github.com/jhojin7/light-controller/tree/main/sticks3).

## Install CircuitPython

1. Download the UF2 for the [Reverse TFT Feather](https://circuitpython.org/board/adafruit_feather_esp32s3_reverse_tft/).
2. Connect the board with a USB data cable and double-click Reset.
3. Copy the UF2 to the boot drive, usually named `FTHRS3BOOT`.
4. Wait for the board to restart and mount as `CIRCUITPY`.

Download the [Adafruit library bundle](https://circuitpython.org/libraries)
matching the installed CircuitPython major version. Copy these into `CIRCUITPY/lib/`:

- `adafruit_display_text/`
- `adafruit_requests.mpy` (or its folder)
- `adafruit_connection_manager.mpy` (or its folder)

## Install the controller

Copy `code.py` and `boot.py` to the CIRCUITPY root. Create `config.json` and
`settings.toml` from the supplied templates, following the
[configuration reference](CONFIGURATION.md), then copy them to the same root.

Reset the board. **D1** cycles modes; **D2** applies. The large D0/BOOT button
controls sleep: hold it for one second, then release. The controller also
sleeps after 15 seconds without input. D1 or D2 wakes it; release before the
next browse/apply press. Sleep/wake does not change the light.

The selected preset and last command survive sleep. Wi-Fi reconnects on wake
with a five-second connection timeout. USB keeps CircuitPython in simulated
sleep; disconnect USB for battery-only deep sleep. See [sleep details](FEATHER_SLEEP.md).

The header shows battery percentage from the built-in MAX17048 gauge and
refreshes every 15 seconds while awake. At 20% or below it turns red. `--%`
means the gauge could not be read; no extra library is required.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No CIRCUITPY drive | USB data cable, correct UF2 and boot mode |
| Blank display | Press D1/D2 to wake; if still blank, Reset and check application/libraries |
| Upside-down display | Change `display.rotation` from `90` to `270` in `code.py` |
| Wi-Fi failure | SSID/password, 2.4 GHz network and signal; reset after corrections |
| HA error | URL reachability, token and exact light entity ID |
| Buttons do nothing | Use D1/D2; inspect serial output at 115200 baud |

For automated checks and serial recovery, see [TESTING.md](TESTING.md).
