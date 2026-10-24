#!/usr/bin/env python3
"""Compile the actual portable C++ controller/renderer and exercise behavior traces."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from scenarios import scenarios, off_scenarios


def build():
    candidates = list((ROOT / ".pio/libdeps").glob("*/ArduinoJson/src/ArduinoJson.h"))
    if not candidates:
        raise SystemExit("Install dependencies first: .venv/bin/pio pkg install -e sticks3")
    output = ROOT / ".local/harness"
    output.parent.mkdir(exist_ok=True)
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-I" + str(ROOT / "include"), "-I" + str(candidates[0].parent),
                    str(ROOT / "src/controller.cpp"), str(ROOT / "src/screen.cpp"),
                    str(ROOT / "tests/harness.cpp"), "-o", str(output)], check=True)
    return output


def run_cases(binary):
    fixture = json.loads((ROOT / "tests/fixtures/modes.json").read_text())
    cases = scenarios(fixture) + off_scenarios(fixture)
    cases += [
        {"name": "battery-full", "battery": 100,
         "config": {"entity_id": "light.fixture", "modes": [fixture["modes"][1]]},
         "frames": [{"visible": ["100%"]}]},
        {"name": "battery-low", "battery": 7, "frames": [{"visible": ["7%"]}]},
        {"name": "battery-charging", "battery": 92, "charging": True, "frames": [{"visible": ["92%"]}]},
        {"name": "invalid-config-never-sends", "config": {"entity_id": "switch.wrong", "modes": fixture["modes"]},
         "frames": [{"confirm": True, "visible": ["ERROR", "CONFIG ERROR"]}]},
        {"name": "invalid-brightness-never-sends", "config": {"entity_id": "light.fixture", "modes": [{"name": "BAD", "brightness": 256, "kelvin": 4000}]},
         "frames": [{"confirm": True, "visible": ["ERROR", "CONFIG ERROR"]}]},
        {"name": "explicit-icon", "config": {"entity_id": "light.fixture", "modes": [{"name": "DAY", "brightness": 255, "kelvin": 5000, "icon": "moon"}]},
         "frames": [{"icon": "moon"}]},
    ]
    for case in cases:
        if "config" not in case:
            case["config"] = fixture
    process = subprocess.run([str(binary)], input="\n".join(json.dumps(c) for c in cases) + "\n",
                             text=True, capture_output=True, check=True)
    outputs = [json.loads(line) for line in process.stdout.splitlines()]
    if len(outputs) != len(cases):
        raise AssertionError("harness did not complete all scenarios")
    for case, output in zip(cases, outputs):
        assert len(output["frames"]) == len(case["frames"]), case["name"]
        for expected, frame in zip(case["frames"], output["frames"]):
            assert not frame["clipped"], case["name"] + ": out-of-bounds drawing"
            for text in expected.get("visible", []):
                assert text in frame["visible"], (case["name"], text, frame["visible"])
            for text in expected.get("absent", []):
                assert text not in frame["visible"], (case["name"], text)
            if "icon" in expected:
                assert expected["icon"] == frame["icon"], case["name"]
            if "redraw" in expected:
                assert expected["redraw"] == frame["redraw"], case["name"]
        assert [p["body"] for p in output["posts"]] == case.get("posts", []), case["name"]
        assert [p["service"] for p in output["posts"]] == case.get("services", ["turn_on"] * len(case.get("posts", []))), case["name"]
        print("PASS " + case["name"])
    return len(cases)


def interaction_checks():
    candidates = list((ROOT / ".pio/libdeps").glob("*/ArduinoJson/src/ArduinoJson.h"))
    output = ROOT / ".local/interaction-tests"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-I" + str(ROOT / "include"), "-I" + str(candidates[0].parent),
                    str(ROOT / "src/controller.cpp"), str(ROOT / "src/interaction.cpp"),
                    str(ROOT / "src/screen.cpp"), str(ROOT / "tests/interaction_test.cpp"),
                    "-o", str(output)], check=True)
    subprocess.run([str(output)], check=True)


if __name__ == "__main__":
    count = run_cases(build())
    interaction_checks()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(f"PASS {count} C++ behavior scenarios and {result.testsRun} provisioning checks")
