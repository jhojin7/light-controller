# Light Mode Controller Setup Guide

Simple guide to get your physical light controller working with Home Assistant.

**What you need:**
- Adafruit ESP32-S3 Reverse TFT Feather (product 5691)
- A computer with a USB-C cable (data cable, not charge-only)
- Home Assistant already running with your SmartThings lights added
- Your WiFi name and password

---

## Part 1: Install CircuitPython on the board

1. Go to this page in a browser:
   https://circuitpython.org/board/adafruit_feather_esp32s3_reverse_tft/

2. Download the latest **.uf2** file (the big blue button).

3. Plug the Feather into your computer with a USB-C cable.

4. Double-click the **Reset** button on the board.
   (There is a Reset button on both sides. The RGB LED will turn green or purple.)

5. A new drive called **FTHRS3BOOT** (or similar) will appear on your computer.

6. Drag the downloaded **.uf2** file onto that drive.

7. The board will restart. A new drive called **CIRCUITPY** will appear.
   You are done installing CircuitPython.

---

## Part 2: Copy the project files

1. Download the libraries you need:
   - Go to https://circuitpython.org/libraries
   - Download the **Library Bundle** that matches your CircuitPython version (usually 9.x or 10.x).
   - Unzip it.

2. On the **CIRCUITPY** drive, create a folder named `lib` if it does not exist.

3. From the library bundle, copy these folders/files into the `lib` folder on CIRCUITPY:
   - `adafruit_requests.mpy` (or the folder)
   - `adafruit_connection_manager.mpy` (or the folder)
   - `adafruit_display_text` (the whole folder)

4. From the project folder or deployment ZIP, copy these files onto the root of the **CIRCUITPY** drive:
   - `code.py`
   - `boot.py`
   - `config.json` (copy `config.json.example` with this name when using the source repository)
   - `settings.toml.example`

5. Rename `settings.toml.example` to `settings.toml`.

---

## Part 3: Edit the settings

Open `settings.toml` with any text editor (Notepad, TextEdit, VS Code, etc.) and change these lines:

```
CIRCUITPY_WIFI_SSID = "YourWiFiName"
CIRCUITPY_WIFI_PASSWORD = "YourWiFiPassword"
HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = "your_long_lived_access_token_here"
```

**How to get the Home Assistant token:**
1. Open Home Assistant in a browser.
2. Click your profile picture (bottom left).
3. Scroll down to **Long-Lived Access Tokens**.
4. Click **Create Token**, give it a name like "Light Controller", and copy the long string.
5. Paste it into `settings.toml` between the quotes.

**How to find your light entity ID:**
1. In Home Assistant go to **Settings → Devices & services → Entities**.
2. Find your light (the one controlled by SmartThings).
3. The entity ID looks like `light.living_room` or `light.bedroom_lamp`.
4. Put that exact name into `config.json` (see next step).

Save `settings.toml`.

---

## Part 4: Edit the modes (optional)

Open `config.json` with a text editor.

Change the `entity_id` to your light’s entity ID.

You can change the default modes or add more entries to the list:
- `name` — what shows on the screen
- `brightness` — 0 to 255 (255 = full brightness)
- `kelvin` — color temperature (lower = warmer/yellower, higher = cooler/bluer). Common values: 2200 (very warm), 2700 (warm), 4000 (neutral), 5000–6500 (cool).

The fourth default mode is `{"name": "OFF", "action": "off"}`. It needs no
brightness or Kelvin value. Select it with D1 and press D2 to turn the light off;
select and apply any on preset to turn it back on.

Example:
```json
{
  "entity_id": "light.bedroom",
  "modes": [
    {"name": "DAY", "brightness": 255, "kelvin": 5000},
    {"name": "EVENING", "brightness": 100, "kelvin": 2700},
    {"name": "SLEEP", "brightness": 20, "kelvin": 2200},
    {"name": "OFF", "action": "off"}
  ]
}
```

Save the file.

---

## Part 5: Use it

1. Eject / safely remove the CIRCUITPY drive (or just unplug the board).
2. Plug the board back in (or press Reset once).
3. The screen shows one mode at a time, with its icon, brightness, Kelvin, and a `1/n` position indicator.
4. Press the **D1** button (one of the two smaller buttons near the display) to cycle through modes.
5. Press the **D2** button to apply the highlighted mode to your light.

The top right WiFi icon turns green when connected. The bottom shows the last successfully applied mode and any status messages.

---

## Troubleshooting

- **Screen is blank or upside down**: Press Reset. If still blank, re-copy `code.py`. For the opposite portrait orientation, change `display.rotation = 90` to `display.rotation = 270` in `code.py`.
- **WiFi: -- or WiFi failed**: Double-check the SSID and password in `settings.toml`. Make sure the board is in range.
- **HA error or Request failed**:
  - Check that the HA_URL is correct and the board can reach Home Assistant on your network.
  - Verify the token is correct and has not been deleted.
  - Confirm the entity_id in `config.json` matches exactly (case-sensitive).
- **Buttons do nothing**: D1 cycles, D2 confirms. The big D0/BOOT button is not used for normal operation.
- **Still stuck**: Plug the board into a computer, open a serial monitor (Mu editor or `screen /dev/tty...` or the CircuitPython serial tools) at 115200 baud and look for error messages.

That’s it. Enjoy your physical light mode controller.
