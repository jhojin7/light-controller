"""Exercise real sleep shutdown and timed wake on the connected Feather.

Temporarily installs an instrumented copy of the current firmware. No light
commands are sent. Always restores the repository firmware, leaving settings,
configuration and libraries untouched. USB runs verify simulated sleep only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import fcntl
import struct
import json
import os
from pathlib import Path
import select
import sys
import termios
import time

from board_serial import Board, discover_port

ROOT = Path(__file__).resolve().parents[1]

PROBE = '''
import microcontroller
import supervisor
time.sleep(1)  # Allow the host to attach CDC before the first structured event.

# Reserve the last four bytes for this temporary probe, outside app state.
probe_cycle = alarm.sleep_memory[-4] if alarm.wake_alarm is not None else 0
alarm.sleep_memory[-4] = probe_cycle + 1
if microcontroller.cpu.reset_reason == microcontroller.ResetReason.DEEP_SLEEP_ALARM:
    alarm.sleep_memory[-3] += 1

native_update = update_display
probe_preview_seen = False

def update_display():
    global probe_preview_seen
    native_update()
    if status_text == 'Connecting' and not probe_preview_seen:
        probe_preview_seen = True
        assert selected_index == 1, 'Selection did not survive wake'
        assert applied_mode == modes[0]['name'], 'History did not survive wake'
        print('__SLEEP__' + json.dumps({'event': 'preview', 'cycle': probe_cycle,
            'selected': selected_index, 'history': applied_mode,
            'brightness': display.brightness, 'refresh': display.auto_refresh,
            'usb': supervisor.runtime.usb_connected,
            'reset': str(microcontroller.cpu.reset_reason)}))

class ProbeButton:
    def __init__(self, native, sleep_key=False):
        self.native = native
        self.sleep_key = sleep_key
        self.started = None

    @property
    def value(self):
        if not self.sleep_key:
            return False  # Never send a light command during this probe.
        if self.started is None:
            self.started = time.monotonic()
        elapsed = time.monotonic() - self.started
        # Cycle 0: D0 hold + release. Later cycles: real idle timeout.
        return not (probe_cycle == 0 and 0.5 <= elapsed < 1.8)

    def deinit(self):
        self.native.deinit()

btn_sleep = ProbeButton(btn_sleep, True)
btn_cycle = ProbeButton(btn_cycle)
btn_confirm = ProbeButton(btn_confirm)
if probe_cycle == 0:
    alarm.sleep_memory[-3] = 0
    selected_index = 1
    applied_mode = modes[0]['name']
    applied_action = modes[0].get('action', 'on')
if probe_cycle < 3:
    run()
else:
    restore_sleep_state()
    assert selected_index == 1 and applied_mode == modes[0]['name']
    status_text = 'Connecting'
    update_display()
    wifi.radio.enabled = True
    assert connect_wifi(), 'WiFi did not reconnect'
    response = requests.get(ha_url + '/api/',
        headers={'Authorization': 'Bearer ' + ha_token}, timeout=10)
    assert response.status_code == 200, 'HA read-only authentication failed'
    response.close()
    status_text = 'Sleep test OK'
    update_display()
    print('__SLEEP__' + json.dumps({'event': 'complete', 'cycles': probe_cycle,
        'true_deep_sleep_wakes': alarm.sleep_memory[-3],
        'wifi': wifi_ok, 'ha_read_only': True}))
    while True:
        time.sleep(1)
'''


def instrument(source):
    entry = 'if __name__ == "__main__":\n    run()'
    assert entry in source, 'Application entry point changed'
    sleep = '    alarm.exit_and_deep_sleep_until_alarms(*alarms, preserve_dios=rails)'
    assert sleep in source, 'Sleep entry point changed'
    source = source.replace(sleep, '''    alarms.append(alarm.time.TimeAlarm(monotonic_time=time.monotonic() + 2))
    print('__SLEEP__' + json.dumps({'event': 'shutdown',
        'cycle': probe_cycle, 'rails': [rail.value for rail in rails],
        'wifi_enabled': wifi.radio.enabled, 'brightness': display.brightness,
        'refresh': display.auto_refresh,
        'wake_pins': [str(item.pin) for item in alarms[:2]]}))
''' + sleep)
    return source.replace(entry, PROBE)


def reset_board(board):
    # Reload from flash after host MSC writes, rather than reuse VM/FAT caches.
    board.execute('import microcontroller')
    board._write(b'microcontroller.reset()\x04')
    os.close(board.fd)
    board.fd = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--volume', type=Path, default=Path('/Volumes/CIRCUITPY'))
    parser.add_argument('--timeout', type=float, default=100)
    args = parser.parse_args()
    port = args.port or discover_port()
    source = (ROOT / 'code.py').read_text()
    installed = args.volume / 'code.py'
    output = ROOT / 'dist/sleep' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    (output / 'previous-code.py').write_bytes(installed.read_bytes())
    events = []
    report = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'events': events, 'ok': False}
    try:
        with Board(port) as board:
            board.execute('import supervisor\nsupervisor.runtime.autoreload = False')
            installed.write_text(instrument(source))
            os.sync()
            reset_board(board)
        deadline = time.monotonic() + 10
        time.sleep(1)
        while not Path(port).exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        original = termios.tcgetattr(fd)
        settings = termios.tcgetattr(fd)
        settings[0] = settings[1] = settings[3] = 0
        termios.tcsetattr(fd, termios.TCSANOW, settings)
        fcntl.ioctl(fd, termios.TIOCMBIS, struct.pack('I', termios.TIOCM_DTR))
        pending = b''
        try:
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if not select.select([fd], [], [], 0.25)[0]:
                    continue
                chunk = os.read(fd, 65536)
                report['serial_bytes'] = report.get('serial_bytes', 0) + len(chunk)
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    if line.startswith(b'Traceback') or line.startswith((b'AttributeError:', b'RuntimeError:', b'ValueError:', b'AssertionError:')):
                        print('Probe exception: ' + line.decode(errors='replace').split(':')[0], flush=True)
                    marker = line.find(b'__SLEEP__')
                    if marker >= 0:
                        event = json.loads(line[marker + 9:].strip())
                        events.append(event)
                        print(json.dumps(event), flush=True)
                        if event['event'] == 'complete':
                            previews = [item for item in events if item['event'] == 'preview']
                            shutdowns = [item for item in events if item['event'] == 'shutdown']
                            assert len(previews) == 4 and len(shutdowns) == 3, 'Missing wake/shutdown cycles'
                            assert all(item['brightness'] == 1 and item['refresh'] for item in previews)
                            assert all(item['rails'] == [False, False] and not item['wifi_enabled']
                                       and item['brightness'] == 0 and not item['refresh'] for item in shutdowns)
                            report['ok'] = True
                            return 0
            raise TimeoutError('Sleep probe did not complete')
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, original)
            os.close(fd)
    except Exception as error:
        report['error'] = type(error).__name__
        print('FAIL sleep probe: ' + type(error).__name__, flush=True)
        return 1
    finally:
        # Re-enter REPL before the host write so auto-reload cannot race it.
        try:
            with Board(port) as board:
                board.execute('import supervisor\nsupervisor.runtime.autoreload = False')
                installed.write_text(source)
                os.sync()
                reset_board(board)
        except Exception as error:
            report['ok'] = False
            report['restore_error'] = type(error).__name__
            print('Firmware restore failed; recopy code.py', flush=True)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print('Report: ' + str(output / 'report.json'), flush=True)
        # A restoration error must also fail the process, including a pending return.
        if report.get('restore_error'):
            sys.exit(1)


if __name__ == '__main__':
    raise SystemExit(main())
