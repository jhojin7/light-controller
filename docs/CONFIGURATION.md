# Configuration

Both boards control one Home Assistant light entity using the same presets.
Create local copies of the templates:

```sh
cp config.json.example config.json
cp settings.toml.example settings.toml
```

## Connection settings

Edit `settings.toml`:

```toml
CIRCUITPY_WIFI_SSID = "YourWiFiName"
CIRCUITPY_WIFI_PASSWORD = "YourWiFiPassword"
HA_URL = "http://homeassistant.local:8123"
HA_TOKEN = "your_long_lived_access_token"
```

Use a 2.4 GHz Wi-Fi network. Create a long-lived access token in your Home
Assistant profile. Find the light's entity ID under Settings → Devices & services
→ Entities, then set it in `config.json`.

The `CIRCUITPY_` setting names are also used by the StickS3 provisioner. It
converts them to device JSON without changing the source TOML.

## Modes

```json
{
  "entity_id": "light.bedroom",
  "modes": [
    {"name": "DAY", "brightness": 255, "kelvin": 5000},
    {"name": "EVENING", "brightness": 128, "kelvin": 2700},
    {"name": "SLEEP", "brightness": 25, "kelvin": 2200},
    {"name": "OFF", "action": "off"}
  ]
}
```

| Field | Value |
| --- | --- |
| `entity_id` | Light entity, such as `light.bedroom` |
| `modes` | Nonempty list; navigation wraps after the last entry |
| `name` | Display label; long labels shrink or truncate |
| `action` | `on` (default) or `off` |
| `brightness` | Integer 0–255; required for on modes |
| `kelvin` | Positive integer; required for on modes |
| `icon` | Optional `sun`, `sunset`, `moon` or `off`; otherwise chosen automatically |

OFF needs only `name` and `action`. It sends neither brightness nor Kelvin.
Displayed brightness percentages truncate: 128 is 50%; 25 is 9%.

Use temperatures supported by your light. Integrations may round or clamp values;
see the observed temperature mismatch in [testing notes](TESTING.md#recorded-verification).

## Deploy changes

- **Feather:** copy both local files to the CIRCUITPY root and reset.
- **StickS3:** run `make provision` and `make upload-data` from `sticks3/`.
  For HTTPS, also supply `CA=/path/to/ca.pem` when provisioning.

Settings are read at startup. Local `config.json` and `settings.toml` are ignored
by Git. StickS3 device files, filesystem images and full flash backups contain
credentials in plaintext; do not share them.
