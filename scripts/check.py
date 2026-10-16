"""Validate the firmware project without importing board-only modules."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_project():
    for path in (ROOT / "code.py", ROOT / "boot.py", *sorted((ROOT / "scripts").glob("*.py")), *sorted((ROOT / 'tests').rglob('*.py'))):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    config_path = ROOT / 'config.json.example'
    if not config_path.exists():
        config_path = ROOT / 'config.json'
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("config.json must contain an object")
    entity = config.get("entity_id")
    if not isinstance(entity, str) or not entity.startswith("light.") or len(entity) <= 6:
        raise ValueError("entity_id must be a light entity, such as light.living_room")
    modes = config.get("modes")
    if not isinstance(modes, list) or not modes:
        raise ValueError("modes must be a nonempty list")
    for index, mode in enumerate(modes, 1):
        if not isinstance(mode, dict):
            raise ValueError(f"Mode {index} must contain an object")
        name = mode.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Mode {index} needs a nonempty name")
        action = mode.get('action', 'on')
        if action not in ('on', 'off'):
            raise ValueError(f"Mode {index}: action must be on or off")
        if action == 'off':
            continue
        brightness = mode.get("brightness")
        if type(brightness) is not int or not 0 <= brightness <= 255:
            raise ValueError(f"Mode {index}: brightness must be an integer from 0 to 255")
        kelvin = mode.get("kelvin")
        if type(kelvin) is not int or kelvin <= 0:
            raise ValueError(f"Mode {index}: kelvin must be a positive integer")
        if "icon" in mode and mode["icon"] not in ("sun", "sunset", "moon", "off"):
            raise ValueError(f"Mode {index}: icon must be sun, sunset, moon, or off")

    template = (ROOT / "settings.toml.example").read_text(encoding="utf-8")
    assignments = {
        line.split("=", 1)[0].strip()
        for line in template.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    required = {"CIRCUITPY_WIFI_SSID", "CIRCUITPY_WIFI_PASSWORD", "HA_URL", "HA_TOKEN"}
    if not required <= assignments:
        raise ValueError("settings.toml.example is missing required settings")
    print(f"PASS: Python syntax, {len(modes)} configured modes, and settings template")


if __name__ == "__main__":
    try:
        check_project()
    except (OSError, ValueError, SyntaxError) as error:
        raise SystemExit(f"Check failed: {error}") from error
