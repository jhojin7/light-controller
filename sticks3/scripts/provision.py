#!/usr/bin/env python3
"""Stage private StickS3 LittleFS data from existing local configuration files."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("configuration must be an object")
    entity = config.get("entity_id")
    if not isinstance(entity, str) or not entity.startswith("light.") or len(entity) <= 6:
        raise ValueError("entity_id must name a light")
    modes = config.get("modes")
    if not isinstance(modes, list) or not modes:
        raise ValueError("at least one mode is required")
    for index, mode in enumerate(modes, 1):
        if not isinstance(mode, dict) or not isinstance(mode.get("name"), str) or not mode["name"].strip():
            raise ValueError(f"mode {index} needs a name")
        if mode.get("action", "on") not in ("on", "off"):
            raise ValueError(f"mode {index} has an invalid action")
        if mode.get("action") != "off":
            if type(mode.get("brightness")) is not int or not 0 <= mode["brightness"] <= 255:
                raise ValueError(f"mode {index} needs brightness 0–255")
            if type(mode.get("kelvin")) is not int or not 0 < mode["kelvin"] <= 2147483647:
                raise ValueError(f"mode {index} needs a positive Kelvin value")


def private_write(path, contents):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".stage-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(contents)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stage(config_path, settings_path, destination, ca_path=None):
    # Validate everything before replacing previously provisioned data.
    config = json.loads(config_path.read_text())
    validate_config(config)
    settings = tomllib.loads(settings_path.read_text())
    mapping = {"ssid": "CIRCUITPY_WIFI_SSID", "password": "CIRCUITPY_WIFI_PASSWORD",
               "ha_url": "HA_URL", "ha_token": "HA_TOKEN"}
    device = {}
    for target, source in mapping.items():
        value = settings.get(source)
        if not isinstance(value, str) or (not value and target != "password"):
            raise ValueError(f"settings need {source}")
        device[target] = value.rstrip("/") if target == "ha_url" else value
    url = urlsplit(device["ha_url"])
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("HA_URL needs an http(s) URL without embedded credentials, query or fragment")
    ca = ca_path.read_bytes() if ca_path else None
    if url.scheme == "https" and not ca:
        raise ValueError("HTTPS requires --ca-cert with the server's trusted CA PEM")
    if ca and b"-----BEGIN CERTIFICATE-----" not in ca:
        raise ValueError("CA certificate must be PEM")
    payloads = {"config.json": json.dumps(config).encode(), "settings.json": json.dumps(device).encode()}
    if any(len(data) > 65536 for data in payloads.values()) or (ca and len(ca) > 65536):
        raise ValueError("each device file must be at most 64 KiB")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination, 0o700)
    for name, data in payloads.items():
        private_write(destination / name, data)
    if ca:
        private_write(destination / "ca.pem", ca)
    else:
        (destination / "ca.pem").unlink(missing_ok=True)
    return len(config["modes"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--ca-cert", type=Path)
    args = parser.parse_args()
    try:
        count = stage(args.config, args.settings, ROOT / "data", args.ca_cert)
    except (OSError, ValueError):
        # Parser exceptions can contain whole lines of a credential file.
        raise SystemExit("Provisioning failed: check configuration, required settings, and CA certificate") from None
    print(f"Staged private device settings and {count} modes in ignored data/ (values hidden)")


if __name__ == "__main__":
    main()
