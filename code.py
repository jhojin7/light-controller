# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT

"""
Home Assistant Light Mode Controller - Portrait UI
Adafruit ESP32-S3 Reverse TFT Feather (5691)
Single-mode cards with a built-in dotted bitmap font and mode icons.
D1 = Cycle / Wake, D2 = Confirm / Wake, hold D0 = Sleep
"""

import alarm
import board
board.DISPLAY.root_group = None

import time
import json
import os
import displayio
import terminalio
import digitalio
import wifi
import adafruit_connection_manager
import adafruit_requests
from adafruit_display_text import label

def load_config():
    try:
        with open("/config.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print("Config error:", e)
        return {
            "entity_id": "light.example",
            "modes": [
                {"name": "DAY", "brightness": 255, "kelvin": 5000},
                {"name": "EVENING", "brightness": 128, "kelvin": 2700},
                {"name": "SLEEP", "brightness": 25, "kelvin": 2200},
                {"name": "OFF", "action": "off"},
            ],
        }

config = load_config()
modes = config.get("modes", [])
entity_id = config.get("entity_id", "light.example")
if not modes:
    modes = [{"name": "ERROR", "brightness": 0, "kelvin": 0}]

ssid = os.getenv("CIRCUITPY_WIFI_SSID")
password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123").rstrip("/")
ha_token = os.getenv("HA_TOKEN", "")

# GPIO7 is retained LOW during sleep, including USB simulated sleep.
with digitalio.DigitalInOut(board.TFT_I2C_POWER) as power:
    power.switch_to_output(value=True)

display = board.DISPLAY
if alarm.wake_alarm is not None:
    # USB simulated deep sleep keeps the built-in display object, but its panel
    # lost power. Restore the board's ST7789 initialization before drawing.
    # Source: CircuitPython's adafruit_feather_esp32s3_reverse_tft/board.c.
    for command, data, delay in (
        (0x01, b'', 0.15), (0x11, b'', 0.12), (0x13, b'', 0),
        (0x36, b'\x68', 0), (0xB6, b'\x0a\x82', 0),
        (0x3A, b'\x55', 0.01), (0xB2, b'\x0c\x0c\x00\x33\x33', 0),
        (0xB7, b'\x35', 0), (0xBB, b'\x28', 0), (0xC0, b'\x0c', 0),
        (0xC2, b'\x01\xff', 0), (0xC3, b'\x10', 0),
        (0xC4, b'\x20', 0), (0xC6, b'\x0f', 0), (0xD0, b'\xa4\xa1', 0),
        (0xE0, b'\xd0\x00\x02\x07\x0a\x28\x32\x44\x42\x06\x0e\x12\x14\x17', 0),
        (0xE1, b'\xd0\x00\x02\x07\x0a\x28\x31\x54\x47\x0e\x1c\x17\x1b\x1e', 0),
        (0x21, b'', 0), (0x29, b'', 0.12),
    ):
        display.bus.send(command, data)
        if delay:
            time.sleep(delay)
    # Force MADCTL to be resent even when the simulated wake retains rotation.
    display.rotation = 0
display.auto_refresh = True
display.brightness = 1.0
# CircuitPython uses degrees, rather than Arduino's 0-3 rotation values.
display.rotation = 90  # portrait (135 x 240); use 270 for the other orientation
display.root_group = None

splash = displayio.Group()
display.root_group = splash

# Full black background (uses actual rotated size)
bg = displayio.Bitmap(display.width, display.height, 1)
pal = displayio.Palette(1)
pal[0] = 0x070B12
splash.append(displayio.TileGrid(bg, pixel_shader=pal, x=0, y=0))

# A small, original 5x7 alphabet rendered as separated dots. No font files needed.
DOT_GLYPHS = {
    'A': (14, 17, 17, 31, 17, 17, 17),
    'B': (30, 17, 17, 30, 17, 17, 30),
    'C': (14, 17, 16, 16, 16, 17, 14),
    'D': (30, 17, 17, 17, 17, 17, 30),
    'E': (31, 16, 16, 30, 16, 16, 31),
    'F': (31, 16, 16, 30, 16, 16, 16),
    'G': (14, 17, 16, 23, 17, 17, 15),
    'H': (17, 17, 17, 31, 17, 17, 17),
    'I': (14, 4, 4, 4, 4, 4, 14),
    'J': (7, 2, 2, 2, 18, 18, 12),
    'K': (17, 18, 20, 24, 20, 18, 17),
    'L': (16, 16, 16, 16, 16, 16, 31),
    'M': (17, 27, 21, 21, 17, 17, 17),
    'N': (17, 25, 25, 21, 19, 19, 17),
    'O': (14, 17, 17, 17, 17, 17, 14),
    'P': (30, 17, 17, 30, 16, 16, 16),
    'Q': (14, 17, 17, 17, 21, 18, 13),
    'R': (30, 17, 17, 30, 20, 18, 17),
    'S': (15, 16, 16, 14, 1, 1, 30),
    'T': (31, 4, 4, 4, 4, 4, 4),
    'U': (17, 17, 17, 17, 17, 17, 14),
    'V': (17, 17, 17, 17, 17, 10, 4),
    'W': (17, 17, 17, 21, 21, 21, 10),
    'X': (17, 17, 10, 4, 10, 17, 17),
    'Y': (17, 17, 10, 4, 4, 4, 4),
    'Z': (31, 1, 2, 4, 8, 16, 31),
    '0': (14, 17, 19, 21, 25, 17, 14),
    '1': (4, 12, 4, 4, 4, 4, 14),
    '2': (14, 17, 1, 2, 4, 8, 31),
    '3': (30, 1, 1, 14, 1, 1, 30),
    '4': (2, 6, 10, 18, 31, 2, 2),
    '5': (31, 16, 16, 30, 1, 1, 30),
    '6': (14, 16, 16, 30, 17, 17, 14),
    '7': (31, 1, 2, 4, 8, 8, 8),
    '8': (14, 17, 17, 14, 17, 17, 14),
    '9': (14, 17, 17, 15, 1, 1, 14),
    '%': (25, 25, 2, 4, 8, 19, 19),
    '/': (1, 2, 2, 4, 8, 8, 16),
    '-': (0, 0, 0, 31, 0, 0, 0),
    '.': (0, 0, 0, 0, 0, 12, 12),
    ':': (0, 12, 12, 0, 12, 12, 0),
    '?': (14, 17, 1, 2, 4, 0, 4),
    ' ': (0, 0, 0, 0, 0, 0, 0),
}

BACKGROUND = 0x070B12
WHITE = 0xEDF3FB
MUTED = 0x8291A6
GREEN = 0x7EE7B4
RED = 0xFF8A88
AMBER = 0xFFE49C
PADDING = 8
pal[0] = BACKGROUND


def paint_dot(bitmap, x, y, size):
    for dy in range(size):
        for dx in range(size):
            # Knock off corners on larger dots for a softer matrix appearance.
            if size >= 3 and dx in (0, size - 1) and dy in (0, size - 1):
                continue
            bitmap[x + dx, y + dy] = 1


class DotText(displayio.Group):
    def __init__(self, center_x, y, max_width, max_pitch=5, min_pitch=2):
        super().__init__(x=0, y=y)
        self.center_x = center_x
        self.max_width = max_width
        self.max_pitch = max_pitch
        self.min_pitch = min_pitch
        self.text = ''
        self.bitmap = None
        self.palette = displayio.Palette(2)
        self.palette.make_transparent(0)

    @property
    def bounding_box(self):
        if self.bitmap is None:
            return (0, 0, 0, 0)
        return (0, 0, self.bitmap.width, self.bitmap.height)

    def set_text(self, text, color=WHITE):
        text = ''.join(ch if ch in DOT_GLYPHS else '?' for ch in str(text).upper())
        pitch = self.max_pitch
        while pitch > self.min_pitch and (len(text) * 6 - 2) * pitch + pitch - 1 > self.max_width:
            pitch -= 1
        size = max(1, pitch - 1)
        max_chars = ((self.max_width - size) // pitch + 2) // 6
        if len(text) > max_chars:
            text = text[:max_chars - 3] + '...'
        self.palette[1] = color
        if text == self.text and self.bitmap is not None:
            return
        self.text = text
        width = max(1, (len(text) * 6 - 2) * pitch + size)
        bitmap = displayio.Bitmap(width, 6 * pitch + size, 2)
        for i, ch in enumerate(text):
            for row, bits in enumerate(DOT_GLYPHS[ch]):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        paint_dot(bitmap, (i * 6 + col) * pitch, row * pitch, size)
        tile = displayio.TileGrid(bitmap, pixel_shader=self.palette)
        if len(self):
            self[0] = tile
        else:
            self.append(tile)
        self.bitmap = bitmap
        self.x = self.center_x - width // 2


ICON_ROWS = {
    'sun': (
        '......#......', '......#......', '..#.......#..', '...#.....#...',
        '.....###.....', '....#...#....', '##..#...#..##', '....#...#....',
        '.....###.....', '...#.....#...', '..#.......#..', '......#......', '......#......',
    ),
    'sunset': (
        '......#......', '......#......', '..#.......#..', '...#.....#...',
        '.....###.....', '....#...#....', '...#.....#...', '...#.....#...',
        '...#.....#...', '#############', '.............', '..#########..', '.............',
    ),
    'moon': (
        '.....###.....', '...##........', '..##......#..', '..#......###.',
        '.##.......#..', '.##..........', '.##..........', '.###.........',
        '..###......#.', '..#####...##.', '...########..', '....######...', '.............',
    ),
    'off': (
        '......#......', '......#......', '......#......', '..##..#..##..',
        '.##...#...##.', '.#....#....#.', '.#....#....#.', '.#.........#.',
        '.##.......##.', '..##.....##..', '...#######...', '.....###.....', '.............',
    ),
}


def make_icon(rows, pitch=3):
    size = max(1, pitch - 1)
    bitmap = displayio.Bitmap((len(rows[0]) - 1) * pitch + size, (len(rows) - 1) * pitch + size, 2)
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            if pixel == '#':
                paint_dot(bitmap, x * pitch, y * pitch, size)
    return bitmap


icon_bitmaps = {name: make_icon(rows) for name, rows in ICON_ROWS.items()}
icon_palette = displayio.Palette(2)
icon_palette.make_transparent(0)
mode_icon = displayio.TileGrid(icon_bitmaps['sun'], pixel_shader=icon_palette, x=display.width // 2 - 19, y=32)
splash.append(mode_icon)

# Tiny connection icon: color conveys network state without occupying a text row.
wifi_palette = displayio.Palette(2)
wifi_palette.make_transparent(0)
wifi_icon = displayio.TileGrid(
    make_icon(('..#######..', '.#.......#.', '#..#####..#', '..#.....#..', '....###....', '...#...#...', '.....#.....'), pitch=1),
    pixel_shader=wifi_palette, x=display.width - PADDING - 11, y=10,
)
splash.append(wifi_icon)


def small_label(text, y, color=MUTED, center_x=None):
    lbl = label.Label(terminalio.FONT, text=text, color=color,
                      anchor_point=(0.5, 0),
                      anchored_position=(display.width // 2 if center_x is None else center_x, y))
    splash.append(lbl)
    return lbl


header_label = small_label('LIGHT', 8, WHITE, 23)
battery_label = small_label('--%', 8, center_x=83)
mode_title = DotText(display.width // 2, 80, display.width - 8)
brightness_text = DotText(34, 126, 54, max_pitch=2, min_pitch=1)
kelvin_text = DotText(101, 126, 59, max_pitch=2, min_pitch=1)
page_text = DotText(display.width // 2, 174, display.width - 2 * PADDING, max_pitch=2, min_pitch=1)
for item in (mode_title, brightness_text, kelvin_text, page_text):
    splash.append(item)
brightness_caption = small_label('BRIGHT', 145, center_x=34)
kelvin_caption = small_label('KELVIN', 145, center_x=101)
status_label = small_label('READY', 188)
applied_label = small_label('ON: --', 201)
help_label = small_label('D1 NEXT  D2 SET', 214)
sleep_hint = small_label('D0 HOLD TO SLEEP', 227)

# Subtle rules keep the single-mode card and navigation visually separate.
rule_bitmap = displayio.Bitmap(display.width - 2 * PADDING, 1, 1)
rule_palette = displayio.Palette(1)
rule_palette[0] = 0x233044
for y in (24, 164):
    splash.append(displayio.TileGrid(rule_bitmap, pixel_shader=rule_palette, x=PADDING, y=y))


def set_small_text(lbl, text):
    max_chars = (display.width - 2 * PADDING) // terminalio.FONT.get_bounding_box()[0]
    text = str(text).upper().replace('\n', ' ')
    lbl.text = text if len(text) <= max_chars else text[:max_chars - 3] + '...'


def mode_style(mode):
    if mode.get('action', 'on') == 'off':
        return 'off', 0xAAB7C9
    name = str(mode['name']).upper()
    icon = str(mode.get('icon', '')).lower()
    if icon not in icon_bitmaps:
        if any(word in name for word in ('SLEEP', 'NIGHT', 'BED')):
            icon = 'moon'
        elif any(word in name for word in ('EVENING', 'DUSK', 'SUNSET')):
            icon = 'sunset'
        elif any(word in name for word in ('DAY', 'MORNING')):
            icon = 'sun'
        else:
            icon = 'sun' if mode['kelvin'] >= 4000 else 'sunset' if mode['kelvin'] >= 2500 else 'moon'
    return icon, {'sun': AMBER, 'sunset': 0xFFB580, 'moon': 0xB6BEFF, 'off': 0xAAB7C9}[icon]


# Buttons
btn_sleep = digitalio.DigitalInOut(board.D0)
btn_sleep.switch_to_input(pull=digitalio.Pull.UP)
btn_cycle = digitalio.DigitalInOut(board.D1)
btn_cycle.switch_to_input(pull=digitalio.Pull.DOWN)
btn_confirm = digitalio.DigitalInOut(board.D2)
btn_confirm.switch_to_input(pull=digitalio.Pull.DOWN)

selected_index = 0
applied_mode = "--"
applied_action = None
status_text = "Ready"
wifi_ok = False
requests = None

def update_display():
    mode = modes[selected_index]
    icon, accent = mode_style(mode)
    # Present the whole new mode together, including its icon and page number.
    auto_refresh = display.auto_refresh
    display.auto_refresh = False
    try:
        mode_icon.bitmap = icon_bitmaps[icon]
        icon_palette[1] = accent
        mode_title.set_text(mode['name'], accent)
        is_off = mode.get('action', 'on') == 'off'
        bright_pct = 0 if is_off else int(mode['brightness'] * 100 / 255)
        brightness_text.set_text(f"{bright_pct}%")
        kelvin_text.set_text('--' if is_off else f"{mode['kelvin']}K")
        page_text.set_text(f"{selected_index + 1}/{len(modes)}", MUTED)
        wifi_palette[1] = GREEN if wifi_ok else MUTED
        message = {'Ready': 'D2 TO APPLY', 'Selected': 'D2 TO APPLY', 'OK': 'APPLIED'}.get(status_text, status_text)
        set_small_text(status_label, message)
        if status_text == 'OK':
            status_label.color = GREEN
        elif status_text.startswith(('Err', 'No ', 'WiFi fail', 'Failed')):
            status_label.color = RED
        elif status_text in ('Sending...', 'Connecting'):
            status_label.color = AMBER
        else:
            status_label.color = MUTED
        set_small_text(applied_label, 'LIGHT OFF' if applied_action == 'off' else f"On: {applied_mode}")
        applied_label.color = GREEN if applied_mode == mode['name'] else MUTED
        display.refresh(minimum_frames_per_second=0)
    finally:
        display.auto_refresh = auto_refresh

# MAX17048 SOC register is big-endian, with 1/256 percent per bit. Reading
# directly avoids resetting the gauge or adding new on-board dependencies.
# https://github.com/adafruit/Adafruit_CircuitPython_MAX1704x
battery_bus = board.I2C()


def update_battery():
    if not battery_bus.try_lock():
        battery_label.text = '--%'
        battery_label.color = MUTED
        return
    try:
        data = bytearray(2)
        battery_bus.writeto_then_readfrom(0x36, b'\x04', data)
        percent = min(100, data[0])
        battery_label.text = str(percent) + '%'
        battery_label.color = RED if percent <= 20 else MUTED
    except OSError:
        battery_label.text = '--%'
        battery_label.color = MUTED
    finally:
        battery_bus.unlock()


def connect_wifi():
    global wifi_ok, requests, status_text
    if not ssid or not password:
        status_text = "No WiFi"
        update_display()
        return False
    try:
        wifi.radio.connect(ssid, password, timeout=5)
        pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
        ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
        requests = adafruit_requests.Session(pool, ssl_context)
        wifi_ok = True
        status_text = "WiFi OK"
        return True
    except Exception as e:
        print("WiFi error:", e)
        status_text = "WiFi fail"
        wifi_ok = False
        update_display()
        return False

def apply_mode():
    global applied_mode, applied_action, status_text
    if not wifi_ok or not requests or not ha_token:
        status_text = "No token"
        update_display()
        return
    mode = modes[selected_index]
    status_text = "Sending..."
    update_display()
    is_off = mode.get('action', 'on') == 'off'
    service = 'turn_off' if is_off else 'turn_on'
    url = f"{ha_url}/api/services/light/{service}"
    headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
    payload = {"entity_id": entity_id}
    if not is_off:
        payload.update({
            "brightness": mode["brightness"],
            "color_temp_kelvin": mode["kelvin"],
        })
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            applied_mode = mode["name"]
            applied_action = 'off' if is_off else 'on'
            status_text = "OK"
        else:
            status_text = f"Err {response.status_code}"
        response.close()
    except Exception as e:
        status_text = "Failed"
        print(e)
    update_display()

IDLE_SECONDS = 15
SLEEP_HOLD_SECONDS = 1.0
RELEASE_SECONDS = 0.05


def state_checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def save_sleep_state():
    memory = alarm.sleep_memory
    memory[:4] = b'\0\0\0\0'
    payload = json.dumps([
        state_checksum(json.dumps(config).encode()), selected_index,
        applied_mode, applied_action,
    ]).encode()
    if len(payload) + 10 > len(memory):
        return
    memory[4:6] = len(payload).to_bytes(2, 'little')
    memory[6:10] = state_checksum(payload).to_bytes(4, 'little')
    memory[10:10 + len(payload)] = payload
    memory[:4] = b'LCS1'  # Commit only after the complete record is written.


def restore_sleep_state():
    global selected_index, applied_mode, applied_action
    memory = alarm.sleep_memory
    try:
        if alarm.wake_alarm is None or bytes(memory[:4]) != b'LCS1':
            return
        size = int.from_bytes(memory[4:6], 'little')
        if not 0 < size <= len(memory) - 10:
            return
        payload = bytes(memory[10:10 + size])
        if state_checksum(payload) != int.from_bytes(memory[6:10], 'little'):
            return
        fingerprint, index, previous, action = json.loads(payload.decode())
        if fingerprint != state_checksum(json.dumps(config).encode()):
            return
        if type(index) is not int or not 0 <= index < len(modes):
            return
        if not (previous == '--' and action is None) and not any(
            mode['name'] == previous and mode.get('action', 'on') == action
            for mode in modes
        ):
            return
        selected_index, applied_mode, applied_action = index, previous, action
    except (ValueError, TypeError, KeyError):
        pass
    finally:
        memory[:4] = b'\0\0\0\0'  # Reset/reload must not reuse old history.


def sleep_controller():
    """Called only after button release and after any request has completed."""
    global requests, wifi_ok
    save_sleep_state()
    requests = None
    adafruit_connection_manager.connection_manager_close_all()
    wifi.radio.enabled = False
    wifi_ok = False
    display.auto_refresh = False
    display.brightness = 0
    display.bus.send(0x28, b'')  # Display off, then panel sleep before rail off.
    display.bus.send(0x10, b'')
    time.sleep(0.12)
    btn_sleep.deinit()
    btn_cycle.deinit()
    btn_confirm.deinit()
    rails = []
    for pin in (board.TFT_I2C_POWER, board.NEOPIXEL_POWER):
        rail = digitalio.DigitalInOut(pin)
        rail.switch_to_output(value=False)
        rails.append(rail)
    alarms = [alarm.pin.PinAlarm(pin=pin, value=True) for pin in (board.D1, board.D2)]
    # GPIO7's board reset default is HIGH. Preserve LOW across the VM teardown.
    alarm.exit_and_deep_sleep_until_alarms(*alarms, preserve_dios=rails)


def run():
    """Start the controller; tests can supply external buttons, clock and network."""
    global selected_index, status_text
    restore_sleep_state()
    update_battery()
    # Draw the retained selection before the bounded Wi-Fi connection attempt.
    status_text = "Connecting"
    update_display()
    awake_since = time.monotonic()
    wifi.radio.enabled = True
    connect_wifi()
    status_text = "Ready" if wifi_ok else "WiFi fail"
    update_display()

    last_cycle = 0
    last_confirm = 0
    last_activity = awake_since
    battery_read_at = awake_since
    sleep_pressed_at = None
    sleep_pending = False
    release_since = None
    waking = alarm.wake_alarm is not None
    DEBOUNCE = 0.3

    while True:
        now = time.monotonic()
        if now - battery_read_at >= 15:
            update_battery()
            battery_read_at = now
        cycle = btn_cycle.value
        confirm = btn_confirm.value
        sleep_pressed = not btn_sleep.value  # D0 is active LOW.
        any_pressed = cycle or confirm or sleep_pressed
        if any_pressed:
            last_activity = now
            release_since = None
        elif release_since is None:
            release_since = now
        released = release_since is not None and now - release_since >= RELEASE_SECONDS

        if waking:
            # Consume the complete waking press, including bounce/other held keys.
            if released:
                waking = False
        elif sleep_pressed or sleep_pending:
            if sleep_pressed_at is None and sleep_pressed:
                sleep_pressed_at = now
            if sleep_pressed and now - sleep_pressed_at >= SLEEP_HOLD_SECONDS:
                if not sleep_pending:
                    status_text = "Release to sleep"
                    update_display()
                sleep_pending = True
            if sleep_pending and released:
                sleep_controller()
        else:
            sleep_pressed_at = None
            if cycle and (now - last_cycle) > DEBOUNCE:
                selected_index = (selected_index + 1) % len(modes)
                status_text = "Selected"
                last_cycle = now
                update_display()
            if confirm and (now - last_confirm) > DEBOUNCE:
                apply_mode()
                last_confirm = time.monotonic()
                last_activity = last_confirm  # Never expire while sending a command.
            if released and now - last_activity >= IDLE_SECONDS:
                sleep_controller()
        time.sleep(0.05)


if __name__ == "__main__":
    run()
