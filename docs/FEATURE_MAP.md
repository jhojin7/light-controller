# Behavior and board differences

## Shared behavior

| Feature | Behavior |
| --- | --- |
| Navigation | Next selects a preset and wraps; apply sends it to HA |
| Button timing | Inputs repeat when held, accepted more than 300 ms apart |
| Simultaneous input | Selection changes before apply |
| On preset | `light.turn_on` with entity ID, brightness and `color_temp_kelvin` |
| OFF preset | `light.turn_off` with entity ID only |
| Success | HTTP 200/201 shows APPLIED and remembers the last successful mode |
| Failure | Show an error; preserve the previous applied state |
| Missing credentials/network | Send no light request |
| Display | Dotted titles, automatic or explicit icons, brightness, Kelvin and page counter |
| Configuration | Read at startup; missing/malformed JSON uses built-in defaults |

`ON:`/`LIGHT OFF` records controller commands. Neither version subscribes to
external HA state changes. Network calls block button handling while waiting
for a response. See [configuration](CONFIGURATION.md) and [test coverage](TESTING.md).

## Differences

| Area | Feather | StickS3 |
| --- | --- | --- |
| Runtime | CircuitPython | Arduino / PlatformIO |
| Buttons | D1 next, D2 apply; active high | A next, B apply; M5Unified input handling |
| Display rotation | 90°; opposite 270° | 0; opposite 2 |
| Small captions | CircuitPython terminal font | Built-in uppercase bitmap font |
| Battery indicator | None | Percentage, charging, low-battery color; refreshes every 15 s |
| Backlight | Board defaults | 20 kHz PWM, brightness 128/255 |
| Wi-Fi | Connects at startup; no reconnect | Automatic reconnect and 30 s retry |
| Settings | Read TOML directly | Provisioner converts TOML to LittleFS JSON |
| Invalid structure | Empty modes show ERROR; other missing fields can fail | ERROR card; requests disabled |
| Verification | CircuitPython raw REPL and displayio inspection | Native C++ harness and serial JSON commands |

The Feather can report NO TOKEN when a network session is missing. The Wi-Fi
icon represents startup state on Feather and current connection state on StickS3.
