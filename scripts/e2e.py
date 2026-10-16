"""Run the complete firmware on an ESP32; optionally apply and restore real lights."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys
import uuid
import signal

from board_serial import Board

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.scenarios import scenarios, off_scenarios


def bmp(image):
    width, height = image['width'], image['height']
    colors = image['colors']
    runs = bytes.fromhex(image['runs'])
    indices = b''.join(bytes((runs[index+1],))*runs[index] for index in range(0, len(runs), 2))
    assert len(indices) == width*height, 'Incomplete board image'
    stride = (width*3+3) & ~3
    pixels = bytearray()
    for row in range(height-1, -1, -1):
        for col in range(width):
            color = colors[indices[row*width+col]]
            pixels.extend((color & 255, (color >> 8) & 255, color >> 16))
        pixels.extend(bytes(stride-width*3))
    header = b'BM'+struct.pack('<IHHI', 54+len(pixels), 0, 0, 54)
    header += struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return header+pixels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Serial device; auto-detected when exactly one is attached')
    parser.add_argument('--live', action='store_true', help='Apply each configured preset to the real light, then restore its original state')
    parser.add_argument('--skip-ha', action='store_true', help='Explicitly run board simulations without real HA connectivity checks')
    parser.add_argument('--case', help='Run one simulated scenario by name')
    parser.add_argument('--update-goldens', action='store_true', help='Replace reviewed bitmap baselines; never use to hide a failure')
    parser.add_argument('--prove-tests', action='store_true', help='Verify the suite rejects deliberate in-memory regressions')
    args = parser.parse_args()
    def terminate(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, terminate)
    if args.live and args.skip_ha:
        parser.error('--live and --skip-ha cannot be combined')
    source = (ROOT / 'code.py').read_text()
    fixture = json.loads((ROOT / 'tests/fixtures/modes.json').read_text())
    cases = scenarios(fixture)+off_scenarios(fixture)
    if args.case:
        cases = [case for case in cases if case['name'] == args.case]
        if not cases:
            parser.error('Unknown scenario')
    started = datetime.now(timezone.utc)
    output = ROOT / 'dist/e2e' / started.strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    report = {'started_at': started.isoformat(), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'live': args.live, 'ha_skipped': args.skip_ha, 'results': []}

    def record(result):
        for index, image in enumerate(result.pop('images', [])):
            name = result['name']+'-'+str(index)+'.bmp'
            contents = bmp(image)
            (output / name).write_bytes(contents)
            golden = ROOT / 'tests/golden' / name
            if args.update_goldens:
                golden.write_bytes(contents)
            elif not golden.exists() or golden.read_bytes() != contents:
                result['ok'] = False
                result['reason'] = 'Rendered bitmap differs from reviewed baseline: '+name
            result.setdefault('screenshots', []).append(name)
        report['results'].append(result)
        print(('PASS ' if result['ok'] else 'FAIL ')+result['name']+(': '+result['reason'] if result.get('reason') else ''), flush=True)

    try:
        with Board(args.port) as board:
            report['port'] = board.port
            board.execute((ROOT / 'tests/board_suite.py').read_text())
            board.execute('SOURCE = '+repr(source)+'\nFIXTURE = json.loads('+repr(json.dumps(fixture))+')')
            record(board.rpc('smoke()'))
            for case in cases:
                record(board.rpc('simulate(json.loads('+repr(json.dumps(case))+'))', timeout=55))
            if not args.case:
                for index, title in enumerate(('DAY', 'EVENING', 'SLEEP')):
                    frames = [{}]+[{'cycle': True} for _ in range(index)]
                    frames[-1]['visible'] = [title]
                    spec = {'name': 'screen-'+title.lower(), 'screenshots': True, 'frames': frames}
                    record(board.rpc('simulate(json.loads('+repr(json.dumps(spec))+'))', timeout=55))
                off_config = json.loads((ROOT / 'tests/fixtures/off.json').read_text())
                spec = {'name': 'screen-off', 'config': off_config, 'screenshots': True, 'frames': [{}, {'cycle': True}, {'cycle': True}, {'cycle': True, 'visible': ['OFF', '0%', '--', '4/4']}]}
                record(board.rpc('simulate(json.loads('+repr(json.dumps(spec))+'))', timeout=55))
                override = json.loads(json.dumps(fixture))
                override['modes'][0]['icon'] = 'moon'
                spec = {'name': 'screen-icon-override', 'config': override, 'screenshots': True, 'frames': [{'visible': ['DAY']}]}
                record(board.rpc('simulate(json.loads('+repr(json.dumps(spec))+'))', timeout=55))
            if args.prove_tests:
                controls = [
                    ('rotation', 'display.rotation = 90', 'display.rotation = 1', cases[0]),
                    ('cycle', '(selected_index + 1) % len(modes)', 'selected_index', scenarios(fixture)[0]),
                    ('kelvin-payload', '"color_temp_kelvin": mode["kelvin"]', '"color_temp_kelvin": 1234', scenarios(fixture)[1]),
                    ('off-service', "service = 'turn_off' if is_off else 'turn_on'", "service = 'turn_on'", off_scenarios(fixture)[0]),
                ]
                for name, before, after, case in controls:
                    assert before in source, 'Mutation target needs updating: '+name
                    board.execute('SOURCE = '+repr(source.replace(before, after, 1)))
                    case = dict(case, screenshots=False)
                    rejected = board.rpc('simulate(json.loads('+repr(json.dumps(case))+'))')
                    record({'ok': not rejected['ok'], 'name': 'reject-regression-'+name, 'detected': rejected.get('reason')})
                board.execute('SOURCE = '+repr(source))
            if not args.skip_ha and all(item['ok'] for item in report['results']):
                scene_id = 'light_controller_e2e_'+uuid.uuid4().hex[:12] if args.live else None
                # Save the recovery ID before opening the live session.
                report['recovery_scene'] = 'scene.'+scene_id if scene_id else None
                try:
                    connectivity = board.rpc('live_start('+repr(scene_id)+')')
                    record(connectivity)
                    if args.live and connectivity['ok']:
                        for index in range(connectivity['mode_count']):
                            result = board.rpc('live_apply('+str(index)+')', timeout=50)
                            record(result)
                            if not result['ok']:
                                break
                        if all(item['ok'] for item in report['results']):
                            result = board.rpc('live_apply(0)', timeout=50)
                            result['name'] = 'real-on-after-off'
                            record(result)
                except BaseException:
                    board.cancel_pending()
                    raise
                finally:
                    record(board.rpc('live_finish()', timeout=50))
            elif not args.skip_ha:
                record({'ok': False, 'name': 'real-ha-connectivity', 'reason': 'Not run because board contract tests failed'})
    except (Exception, KeyboardInterrupt) as error:
        # Avoid exception details containing settings or HTTP authorization headers.
        record({'ok': False, 'name': 'test-runner', 'reason': type(error).__name__})
        if report.get('recovery_scene') and not any(item.get('scene_deleted') for item in report['results']):
            print('Recovery snapshot may remain: '+report['recovery_scene'], flush=True)
    report['ok'] = all(item['ok'] for item in report['results'])
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    (output / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (ROOT / 'dist/e2e/latest.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Report: '+str(output / 'report.json'), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
