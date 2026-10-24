#!/usr/bin/env python3
"""Capture a physical wake source with a timer fallback; requires a person at the board."""
import argparse
import time

from board import Board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--source", choices=("b", "motion"), required=True)
    args = parser.parse_args()
    with Board(args.port) as board:
        board.call("maintenance", seconds=120)
        before = board.call("next")
        board.call("sleep_test", seconds=60)
    print("Sleep requested; trigger " + args.source + " wake within 60 seconds", flush=True)
    time.sleep(0.8)
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        try:
            with Board(args.port) as resumed:
                after = resumed.call("status", timeout=0.4)
                if after["view"] == "sleep":
                    continue
                resumed.call("maintenance", seconds=120)
                expected = 1 << (12 if args.source == "b" else 13)
                assert after["wake_cause"] == 3, "Fallback timer fired instead of physical wake"
                assert after["wake_pins"] & expected, "Wrong physical wake source: " + str(after["wake_pins"])
                assert after["selected"] == before["selected"], "Selection lost across wake"
                assert after["motion_ready"], "Motion setup failed after wake"
                print("PASS physical " + args.source + " wake, GPIO mask=" + str(after["wake_pins"]), flush=True)
                return
        except (OSError, RuntimeError, TimeoutError):
            time.sleep(0.1)
    raise AssertionError("No wake captured before deadline")


if __name__ == "__main__":
    main()
