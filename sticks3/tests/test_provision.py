import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provision import stage


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"entity_id": "light.test", "modes": [
            {"name": "DAY", "brightness": 255, "kelvin": 5000}, {"name": "OFF", "action": "off"}]}))
        self.settings = self.root / "settings.toml"
        self.settings.write_text('CIRCUITPY_WIFI_SSID="test"\nCIRCUITPY_WIFI_PASSWORD="a\\\"b"\nHA_URL="http://ha.local:8123/"\nHA_TOKEN="private"\n')
        self.destination = self.root / "data"

    def test_converts_settings_without_changing_sources(self):
        before = self.settings.read_bytes()
        self.assertEqual(stage(self.config, self.settings, self.destination), 2)
        device = json.loads((self.destination / "settings.json").read_text())
        self.assertEqual(device["password"], 'a"b')
        self.assertEqual(device["ha_url"], "http://ha.local:8123")
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(stat.S_IMODE((self.destination / "settings.json").stat().st_mode), 0o600)

    def test_invalid_config_preserves_existing_settings(self):
        stage(self.config, self.settings, self.destination)
        before = (self.destination / "settings.json").read_bytes()
        self.config.write_text('{"modes": []}')
        with self.assertRaises(ValueError):
            stage(self.config, self.settings, self.destination)
        self.assertEqual((self.destination / "settings.json").read_bytes(), before)

    def test_https_requires_ca_and_stages_it(self):
        self.settings.write_text(self.settings.read_text().replace("http://", "https://"))
        with self.assertRaises(ValueError):
            stage(self.config, self.settings, self.destination)
        ca = self.root / "ca.pem"
        ca.write_text("-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----")
        stage(self.config, self.settings, self.destination, ca)
        self.assertEqual((self.destination / "ca.pem").read_bytes(), ca.read_bytes())

    def test_embedded_url_credentials_rejected(self):
        self.settings.write_text(self.settings.read_text().replace("http://ha", "http://user:pass@ha"))
        with self.assertRaises(ValueError):
            stage(self.config, self.settings, self.destination)
