"""Bounded CircuitPython raw-REPL transport using only POSIX/Python stdlib."""

import glob
import json
import os
import select
import termios
import time


def discover_port():
    ports = sorted(glob.glob('/dev/cu.usbmodem*') or glob.glob('/dev/ttyACM*'))
    if len(ports) != 1:
        raise RuntimeError('Specify --port: expected exactly one CircuitPython serial device')
    return ports[0]


class Board:
    def __init__(self, port=None):
        self.port = port or discover_port()
        self.fd = None
        self.original = None

    def _read_until(self, marker, timeout):
        result = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([self.fd], [], [], 0.1)[0]:
                chunk = os.read(self.fd, 65536)
                if not chunk:
                    raise RuntimeError('Board disconnected')
                result.extend(chunk)
                if marker in result:
                    return bytes(result)
        # Never include arbitrary serial output: it may contain credentials.
        raise TimeoutError('Board did not respond before the serial deadline')

    def _write(self, data):
        view = memoryview(data)
        while view:
            try:
                sent = os.write(self.fd, view)
                view = view[sent:]
            except BlockingIOError:
                select.select([], [self.fd], [], 0.1)

    def __enter__(self):
        self.fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.original = termios.tcgetattr(self.fd)
        settings = termios.tcgetattr(self.fd)
        settings[0] = settings[1] = settings[3] = 0
        settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        settings[4] = settings[5] = termios.B115200
        settings[6][termios.VMIN] = settings[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, settings)
        try:
            # A running Wi-Fi connection can briefly delay KeyboardInterrupt.
            for attempt in range(4):
                self._write(b'\x02')
                time.sleep(0.1)
                self._write(b'\x03\x03')
                time.sleep(0.25)
                self._write(b'\r')
                try:
                    self._read_until(b'>>>', 4)
                    break
                except TimeoutError:
                    if attempt == 3:
                        raise
            self._write(b'\x01')
            self._read_until(b'raw REPL; CTRL-B to exit\r\n>', 5)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def execute(self, code, timeout=40):
        payload = code.encode('utf-8')
        for offset in range(0, len(payload), 128):
            self._write(payload[offset:offset + 128])
            time.sleep(0.01)
        self._write(b'\x04')
        result = self._read_until(b'\x04>', timeout)
        output, error = result.split(b'\x04')[:2]
        if error:
            # Controlled test assertions are returned by rpc(), not this channel.
            category = next((name for name in ('SyntaxError', 'IndentationError', 'MemoryError', 'NameError', 'OSError', 'RuntimeError') if name.encode() in error), 'BoardError')
            raise RuntimeError('Board probe failed: '+category+'; raw traceback suppressed to protect settings')
        return output.decode('utf-8').removeprefix('OK')

    def rpc(self, expression, timeout=40):
        output = self.execute(
            "print('__E2E__' + json.dumps(" + expression + '))', timeout
        )
        for line in output.splitlines():
            if line.startswith('__E2E__'):
                return json.loads(line[len('__E2E__'):])
        raise RuntimeError('Board probe returned no structured test result')

    def cancel_pending(self):
        """Regain raw mode after a timeout before attempting light restoration."""
        self._write(b'\x03')
        self._read_until(b'>', 8)

    def __exit__(self, *_):
        if self.fd is not None:
            try:
                # Interrupt a timed-out probe, exit raw mode, restart installed firmware.
                self._write(b'\x03')
                time.sleep(0.25)
                self._write(b'\x02')
                time.sleep(0.25)
                self._write(b'\x04')
                time.sleep(0.5)
            finally:
                termios.tcsetattr(self.fd, termios.TCSANOW, self.original)
                os.close(self.fd)
                self.fd = None
