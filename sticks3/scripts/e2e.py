#!/usr/bin/env python3
"""Verify real StickS3 firmware; --live also applies presets and restores the light."""
import argparse
import json
from pathlib import Path
import signal
import ssl
import struct
import subprocess
import time
import urllib.request
import uuid

from board import Board
from check import build
from frame import decode_runs, png

ROOT = Path(__file__).resolve().parents[1]


class HA:
    def __init__(self):
        self.settings = json.loads((ROOT / "data/settings.json").read_text())
        self.config = json.loads((ROOT / "data/config.json").read_text())
        self.context = ssl.create_default_context(cafile=str(ROOT / "data/ca.pem")) if self.settings["ha_url"].startswith("https:") else None

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.settings["ha_url"] + path, data=data, headers={
            "Authorization": "Bearer " + self.settings["ha_token"], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=10) as response:
                return json.load(response)
        except Exception:
            raise RuntimeError("Home Assistant request failed (private response suppressed)") from None

    def state(self):
        return self.call("/api/states/" + self.config["entity_id"])

    def wait(self, predicate):
        deadline = time.monotonic() + 20
        state = None
        while time.monotonic() < deadline:
            state = self.state()
            if predicate(state):
                return state
            time.sleep(0.5)
        observed = {"state": state.get("state"), "brightness": state.get("attributes", {}).get("brightness"),
                    "color_mode": state.get("attributes", {}).get("color_mode"),
                    "kelvin": state.get("attributes", {}).get("color_temp_kelvin")} if state else None
        raise AssertionError("Light did not reach the expected state; observed " + json.dumps(observed))


def matches(actual, expected):
    if actual["state"] != expected["state"]:
        return False
    if expected["state"] == "off":
        return True
    a, e = actual["attributes"], expected["attributes"]
    if "brightness" in e and abs(a.get("brightness", -1000) - e["brightness"]) > 3:
        return False
    mode = e.get("color_mode")
    if mode and a.get("color_mode") != mode:
        return False
    if mode == "color_temp":
        return abs(a.get("color_temp_kelvin", -1000) - e["color_temp_kelvin"]) <= 100
    key = {"hs": "hs_color", "xy": "xy_color", "rgb": "rgb_color", "rgbw": "rgbw_color", "rgbww": "rgbww_color"}.get(mode)
    if key and key in e:
        x, y = a.get(key, []), e[key]
        tolerance = 0.01 if mode == "xy" else 1
        return len(x) == len(y) and all(abs(i - j) <= tolerance for i, j in zip(x, y))
    return True


def live(board, ha):
    before = ha.state()
    assert before["state"] in ("on", "off"), "Light is unavailable"
    attrs = before.get("attributes", {})
    assert "color_temp" in attrs.get("supported_color_modes", []), "Light lacks color temperature support"
    for mode in ha.config["modes"]:
        if mode.get("action") != "off":
            assert mode["brightness"] > 0, "Live test requires nonzero on-mode brightness"
            assert attrs.get("min_color_temp_kelvin", 0) <= mode["kelvin"] <= attrs.get("max_color_temp_kelvin", 100000), "Preset exceeds supported Kelvin range"
    scene_id = "sticks3_recovery_" + uuid.uuid4().hex[:12]
    scene = "scene." + scene_id
    recovery = ROOT / ".local/live-recovery.json"
    recovery.write_text(json.dumps({"scene": scene, "before": before}))
    recovery.chmod(0o600)
    # Retain the scene name even if creation times out after reaching HA.
    created = False
    mismatches = []
    try:
        ha.call("/api/services/scene/create", {"scene_id": scene_id, "snapshot_entities": [ha.config["entity_id"]]})
        created = True
        start = board.call("status")["selected"]
        # Test OFF followed by an on preset as well as each individual preset.
        order = list(range(len(ha.config["modes"])))
        on = next((i for i, m in enumerate(ha.config["modes"]) if m.get("action") != "off"), None)
        if on is not None and any(m.get("action") == "off" for m in ha.config["modes"]):
            order.append(on)
        for index in order:
            current = board.call("status")["selected"]
            for _ in range((index - current) % len(ha.config["modes"])):
                board.call("next")
            result = board.call("apply")
            assert result["status"] == "OK", "Firmware preset request failed: " + result["status"]
            mode = ha.config["modes"][index]
            expected = {"state": "off", "attributes": {}} if mode.get("action") == "off" else {
                "state": "on", "attributes": {"brightness": mode["brightness"], "color_mode": "color_temp", "color_temp_kelvin": mode["kelvin"]}}
            try:
                ha.wait(lambda state: matches(state, expected))
                print(f"PASS real preset {index + 1}", flush=True)
            except AssertionError as error:
                # Complete OFF/back-ON and restoration even if one preset's
                # device-reported temperature differs from the requested value.
                mismatches.append(f"preset {index + 1}: {error}")
                print(f"FAIL real preset {index + 1}: {error}", flush=True)
        for _ in range((start - board.call("status")["selected"]) % len(ha.config["modes"])):
            board.call("next")
    finally:
        try:
            if not created:
                # Creation may have succeeded despite a client timeout. Query it
                # before assuming restoration is impossible.
                ha.call("/api/states/" + scene)
            ha.call("/api/services/scene/turn_on", {"entity_id": scene})
            ha.wait(lambda state: matches(state, before))
            ha.call("/api/services/scene/delete", {"entity_id": scene})
            recovery.unlink()
            print("PASS original light state restored; temporary scene deleted", flush=True)
        except Exception:
            print("RESTORATION NEEDS ATTENTION: recovery details retained in .local/live-recovery.json", flush=True)
            raise
    if mismatches:
        raise AssertionError("; ".join(mismatches))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--skip-ha", action="store_true")
    parser.add_argument("--sleep", action="store_true", help="Also verify timer-woken deep sleep and retained selection")
    args = parser.parse_args()
    if args.live and args.skip_ha:
        parser.error("--live cannot be combined with --skip-ha")
    binary = build()
    config = json.loads((ROOT / "data/config.json").read_text())
    with Board(args.port) as board:
        board.call("maintenance", seconds=120)
        status = board.call("status")
        assert status["board"] == "StickS3", "Unexpected board"
        assert (status["width"], status["height"]) == (135, 240), "Wrong display orientation"
        assert status["psram"] > 8000000, "PSRAM initialization failed"
        assert status["filesystem"] and status["settings"] and status["config_valid"], "Configuration did not load"
        assert status["mode_count"] == len(config["modes"]), "Wrong mode count"
        assert status["motion_ready"], "Motion sensor/IRQ setup failed"
        print("PASS board identity, portrait display, PSRAM and configuration", flush=True)
        start = status["selected"]
        for _ in config["modes"]:
            status = board.call("next")
            assert status["mode"] == config["modes"][status["selected"]]["name"]
            assert not status["clipped"], "Clipped framebuffer"
        assert status["selected"] == start, "Navigation did not wrap"
        print("PASS on-device navigation and wrap", flush=True)
        capture = board.call("frame")
        status = capture["state"]
        pixels = decode_runs(capture)
        png(ROOT / ".local/device-screen.png", pixels)
        # Compare the actual board's frame with an independent host execution
        # of the same renderer; the protocol never exports private settings.
        render_frames = [{"cycle": True} for _ in range(status["selected"])] + [{"cycle": True} for _ in config["modes"]]
        render_frames[-1]["render_status"] = status["status"]
        spec = {"config": config, "frames": render_frames, "online": status["online"],
                "dump": str(ROOT / ".local/host-frame.raw"),
                "battery": status["battery"], "charging": status["charging"],
                "has_applied": status["has_applied"], "applied_name": status["applied_name"], "applied_off": status["applied_off"]}
        subprocess.run([str(binary)], input=json.dumps(spec) + "\n", text=True, stdout=subprocess.DEVNULL, check=True)
        expected = list(struct.unpack("<32400H", (ROOT / ".local/host-frame.raw").read_bytes()))
        assert pixels == expected, "Board framebuffer differs from host renderer"
        print("PASS device framebuffer matches host renderer", flush=True)
        if not args.skip_ha:
            result = board.call("ha_check")
            assert result["online"] and result["ha_http"] == 200 and result["entity_http"] == 200, "Board cannot authenticate with HA or read the light"
            print("PASS device Wi-Fi, HA authentication and light lookup", flush=True)
        if args.live:
            live(board, HA())
        if args.sleep:
            sleep_cycle(board, args.port)


def sleep_cycle(board, port):
    # A non-default selection makes this test fail if RTC retention is lost.
    board.call("next")
    before = board.call("status")
    board.call("sleep_test", seconds=2)
    board.close()
    time.sleep(3)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with Board(port) as resumed:
                after = resumed.call("status", timeout=1)
                assert after["wake_cause"] == 4, "Expected ESP timer wake after deep sleep"
                assert after["selected"] == before["selected"], "Selection lost across deep sleep"
                assert after["applied_name"] == before["applied_name"], "Command history lost across deep sleep"
                assert after["motion_ready"], "Motion setup failed after deep sleep"
                assert after["backlight_pwm_hz"] == 20000, "Backlight PWM changed after wake"
                resumed.call("maintenance", seconds=0)
                print("PASS actual deep sleep, timer wake, retained selection/history and motion reinitialization", flush=True)
                return
        except (OSError, RuntimeError, TimeoutError):
            time.sleep(0.2)
    raise AssertionError("Board did not return after timed deep sleep")


if __name__ == "__main__":
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        main()
    except Exception as error:
        # Omit arbitrary exception contents (may contain network/settings data).
        detail = str(error) if isinstance(error, AssertionError) else type(error).__name__ + "; private details suppressed"
        raise SystemExit("E2E failed: " + detail) from None
