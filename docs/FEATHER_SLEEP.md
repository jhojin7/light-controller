# Feather sleep and wake

## Behavior

The Reverse TFT Feather keeps D1 next and D2 apply. Hold D0 for one second,
then release all buttons to sleep. A shorter D0 press does nothing. D0 takes
priority over navigation/apply while held. After 15 seconds without button
activity, the controller also sleeps. A running HA request finishes or times
out before sleeping; completing a request starts a fresh inactivity window.

D1 or D2 wakes the controller. Both active-high alarm inputs retain an internal
pull-down while asleep (`PinAlarm(value=True, pull=True)`); the awake
`DigitalInOut` pull-downs alone do not survive alarm setup. Idle sleep must stay
asleep without a button press, including while connected to USB for charging. The waking press is consumed: release all
buttons before browsing or applying. Sleep/wake never sends a light command.
The previous selection and last successful command survive sleep in RTC memory;
reset, changed configuration, or invalid retained data starts with safe defaults.
Wake draws the selection before reconnecting Wi-Fi. Connection attempts are
bounded; failure leaves the controller usable and able to sleep.

Sleep disables Wi-Fi, stops display refresh/backlight, and disables TFT/STEMMA
and NeoPixel power. The display must initialize correctly on every wake,
including CircuitPython's USB-connected simulated sleep. D0 remains the BOOT
button; D0 + Reset enters the bootloader. Motion wake needs an external sensor.

## Battery display

Show MAX17048 state of charge as an integer percentage in the header on every
startup/wake and refresh after 15 seconds while awake. Clamp to 0–100%; show
20% or below in red. Fractional SOC is truncated (1.98% displays as 1%). A missing/busy gauge shows `--%` without blocking input or
sleep. Reading the SOC register does not reset the gauge or require additional
CircuitPython libraries. USB presence alone is not a charging indication. The value is the gauge
estimate, not a voltage-to-percentage lookup; do not quick-start/reset the
gauge on every wake.

## Verification requirements

- Host and board tests exercise hold/release, idle deadlines, activity reset,
  wake press consumption, retention, invalid state/configuration, request
  failure, and no HA commands from sleep/wake.
- Real hardware exercises the shutdown path, both wake pin configurations,
  repeated wake/display initialization, and real Wi-Fi/HA read-only connectivity.
- Existing renderer, navigation, OFF request and package checks still pass.
- Report USB simulated sleep separately from battery-only deep sleep and
  measured current. No battery-life/current claims without measurement.

## Hardware references

- [Adafruit pinouts](https://learn.adafruit.com/esp32-s3-reverse-tft-feather/pinouts):
  D0 active low, D1/D2 active high; D1/D2 support sleep wake.
- [Power management](https://learn.adafruit.com/esp32-s3-reverse-tft-feather/power-management):
  `TFT_I2C_POWER` and `NEOPIXEL_POWER` control peripheral rails.
- [CircuitPython alarm](https://docs.circuitpython.org/en/latest/shared-bindings/alarm/index.html):
  deep sleep restarts the application; USB can retain a simulated sleep session;
  `sleep_memory` retains state and `preserve_dios` retains power control levels.
