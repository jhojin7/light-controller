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
is not used for light control.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No CIRCUITPY drive | USB data cable, correct UF2 and boot mode |
| Blank display | Reset and recopy the application and matching libraries |
| Upside-down display | Change `display.rotation` from `90` to `270` in `code.py` |
| Wi-Fi failure | SSID/password, 2.4 GHz network and signal; reset after corrections |
| HA error | URL reachability, token and exact light entity ID |
| Buttons do nothing | Use D1/D2; inspect serial output at 115200 baud |

For automated checks and serial recovery, see [TESTING.md](TESTING.md).
