"""Bounded JSON serial client for the StickS3 firmware (not a Python REPL)."""
import json
import time
import serial
from serial.tools import list_ports


def discover():
    ports = [p.device for p in list_ports.comports() if p.vid == 0x303A and p.pid == 0x1001]
    if len(ports) != 1:
        raise RuntimeError("Specify --port: expected exactly one Espressif USB serial device")
    return ports[0]


class Board:
    def __init__(self, port=None):
        self.port = serial.Serial(port or discover(), 115200, timeout=0.2, write_timeout=2, exclusive=True)

    def call(self, command, timeout=30):
        self.port.write(json.dumps({"cmd": command}).encode() + b"\n")
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline:
            data.extend(self.port.read_until(b"\n"))
            if len(data) > 500000:
                raise RuntimeError("Board response too large")
            if not data.endswith(b"\n"):
                continue
            try:
                result = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                # Boot messages are never repeated in exceptions or logs.
                data.clear()
                continue
            if "error" in result:
                raise RuntimeError("Board rejected command")
            return result
        raise TimeoutError("Board did not answer the JSON command before the deadline")

    def close(self):
        self.port.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
