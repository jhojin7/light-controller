"""Runs on CircuitPython; exercises the complete application entry point.

Only external inputs (files, network, time, buttons) are adapted. The real
displayio renderer, terminal font, application functions and run loop execute.
"""
import gc
import io
import json
import displayio

SOURCE = ''  # Supplied in RAM by the host runner; never written to CIRCUITPY.
FIXTURE = {}


def smoke():
    namespace = {'__name__': 'controller_e2e'}
    pins = []
    try:
        exec(SOURCE, namespace)
        pins = [namespace['btn_cycle'], namespace['btn_confirm'], namespace['btn_sleep']]
        assert callable(namespace.get('run')), 'Application needs an import-safe run() entry point'
        return {'ok': True, 'name': 'entry-point'}
    except AssertionError as error:
        return {'ok': False, 'name': 'entry-point', 'reason': str(error)}
    finally:
        for pin in pins:
            pin.deinit()
        if namespace.get('display'):
            namespace['display'].root_group = None
        namespace.clear()
        gc.collect()


class StopFrames(Exception):
    pass


class Radio:
    enabled = True

    def __init__(self, fail=False):
        self.fail = fail

    def connect(self, *_, **kwargs):
        if self.fail:
            raise OSError('simulated network failure')


class Wifi:
    def __init__(self, fail=False):
        self.radio = Radio(fail)


class Manager:
    def connection_manager_close_all(self):
        pass

    def get_radio_socketpool(self, _):
        return None

    def get_radio_ssl_context(self, _):
        return None


class Response:
    def __init__(self, status):
        self.status_code = status
        self.closed = False

    def close(self):
        self.closed = True


class Session:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.posts = []
        self.responses = []
        self.clock = None
        self.latency = 0

    def post(self, url, json, headers, timeout):
        if self.clock:
            self.clock.offset += self.latency
        self.posts.append({'url': url, 'body': json, 'authorization': headers.get('Authorization'), 'timeout': timeout})
        outcome = self.outcomes[min(len(self.posts) - 1, len(self.outcomes) - 1)]
        if outcome == 'raise':
            raise OSError('simulated request failure')
        response = Response(outcome)
        self.responses.append(response)
        return response


class Requests:
    def __init__(self, session):
        self.session = session

    def Session(self, *_):
        return self.session


def text_blocks(group, ox=0, oy=0, scale=1):
    if group.hidden:
        return []
    ox += group.x * scale
    oy += group.y * scale
    scale *= group.scale
    if hasattr(group, 'text'):
        if not group.text:
            return []
        x, y, width, height = group.bounding_box
        return [(group.text, ox+x*scale, oy+y*scale, width*scale, height*scale)]
    blocks = []
    for child in group:
        if isinstance(child, displayio.Group):
            blocks.extend(text_blocks(child, ox, oy, scale))
    return blocks


def assert_layout(namespace):
    screen = namespace['display']
    assert (screen.width, screen.height) == (135, 240), 'Portrait dimensions changed'
    blocks = text_blocks(screen.root_group)
    for text, x, y, width, height in blocks:
        assert x >= 0 and y >= 0 and x+width <= screen.width and y+height <= screen.height, 'Clipped text: '+text
    for index, a in enumerate(blocks):
        for b in blocks[index+1:]:
            overlaps = a[1] < b[1]+b[3] and b[1] < a[1]+a[3] and a[2] < b[2]+b[4] and b[2] < a[2]+a[4]
            assert not overlaps, 'Overlapping text: '+a[0]+' / '+b[0]
    assert screen.auto_refresh, 'Refresh left disabled'
    return [block[0] for block in blocks]


def frame_pixels(group):
    """Composite the actual TileGrid/font bitmaps into indexed screen pixels."""
    colors = [0x070B12]
    pixels = bytearray(135*240)

    def draw(item, ox=0, oy=0, scale=1):
        if item.hidden:
            return
        ox += item.x * scale
        oy += item.y * scale
        if isinstance(item, displayio.Group):
            for child in item:
                draw(child, ox, oy, scale*item.scale)
            return
        bitmap, shader = item.bitmap, item.pixel_shader
        tw, th = item.tile_width, item.tile_height
        for row in range(item.height*th):
            for col in range(item.width*tw):
                tile = item[col//tw, row//th]
                sx = (tile % (bitmap.width//tw))*tw + col % tw
                sy = (tile // (bitmap.width//tw))*th + row % th
                pixel = bitmap[sx, sy]
                if shader.is_transparent(pixel):
                    continue
                color = shader[pixel]
                if color not in colors:
                    colors.append(color)
                index = colors.index(color)
                for dy in range(scale):
                    for dx in range(scale):
                        x, y = ox+col*scale+dx, oy+row*scale+dy
                        assert 0 <= x < 135 and 0 <= y < 240, 'Rendered pixel outside display'
                        pixels[y*135+x] = index

    draw(group)
    import binascii
    # Small transfers avoid large JSON allocations on the microcontroller.
    runs = bytearray()
    previous, count = pixels[0], 0
    for pixel in pixels:
        if pixel != previous or count == 255:
            runs.extend((count, previous))
            previous, count = pixel, 0
        count += 1
    runs.extend((count, previous))
    return {'width': 135, 'height': 240, 'colors': colors, 'runs': binascii.hexlify(runs).decode()}


class Clock:
    def __init__(self, namespace, frames, screenshots=False, observer=None):
        self.namespace = namespace
        self.frames = frames
        self.index = 0
        self.screenshots = screenshots
        self.observer = observer
        self.observations = []
        self.images = []
        self.offset = 0

    def monotonic(self):
        return self.frames[self.index].get('time', (self.index+1)*0.5) + self.offset

    def sleep(self, delay):
        if delay != 0.05:
            return
        frame = self.frames[self.index]
        texts = assert_layout(self.namespace)
        for expected in frame.get('visible', []):
            assert expected in texts, 'Expected visible text: '+expected
        for forbidden in frame.get('absent', []):
            assert forbidden not in texts, 'Unexpected visible text: '+forbidden
        self.observations.append(texts)
        if self.observer:
            self.observer(frame, texts)
        if self.screenshots and self.index == len(self.frames)-1:
            self.images.append(frame_pixels(self.namespace['display'].root_group))
        self.index += 1
        if self.index >= len(self.frames):
            raise StopFrames()


class Button:
    def __init__(self, clock, key):
        self.clock = clock
        self.key = key

    def deinit(self):
        pass

    @property
    def value(self):
        frame = self.clock.frames[self.clock.index]
        return not frame.get('sleep', False) if self.key == 'sleep' else frame.get(self.key, False)


class BatteryBus:
    def __init__(self, samples=None, busy=False):
        self.samples = list(samples or [0x4980])  # 73.5 percent
        self.busy = busy
        self.locked = False
        self.reads = 0

    def try_lock(self):
        if self.busy:
            return False
        assert not self.locked, 'Battery I2C lock leaked'
        self.locked = True
        return True

    def writeto_then_readfrom(self, address, register, data):
        assert address == 0x36 and register == b'\x04', 'Wrong battery register'
        sample = self.samples[min(self.reads, len(self.samples)-1)]
        self.reads += 1
        if sample == 'fail':
            raise OSError('simulated absent gauge')
        data[0], data[1] = sample >> 8, sample & 255

    def unlock(self):
        self.locked = False


class SleepRequested(Exception):
    pass


class Alarm:
    def __init__(self, waking=False, memory=None):
        self.wake_alarm = object() if waking else None
        self.sleep_memory = bytearray(4096) if memory is None else memory
        self.pin = self
        self.calls = []

    def PinAlarm(self, pin, value, pull=False):
        return (str(pin), value, pull)

    def exit_and_deep_sleep_until_alarms(self, *alarms, preserve_dios=()):
        assert len(alarms) == 2 and all(item[1] for item in alarms), 'Need two active-high wake alarms'
        assert all(item[2] for item in alarms), 'Wake inputs lost their inactive bias during sleep'
        assert all(not rail.value for rail in preserve_dios), 'Peripheral rail was left on'
        self.calls.append({'wake_pins': [item[0] for item in alarms], 'rails_off': len(preserve_dios)})
        raise SleepRequested()


class Output:
    def __init__(self, pin):
        self.pin = pin
        self.value = None

    def switch_to_output(self, value):
        self.value = value


class Digital:
    DigitalInOut = Output


class Bus:
    def __init__(self):
        self.commands = []

    def send(self, command, data):
        self.commands.append(command)


class Screen:
    """Keep the native renderer; adapt only panel power/commands during sleep."""
    def __init__(self, native):
        self.native = native
        self.bus = Bus()
        self.brightness = 1.0
        self.auto_refresh = True

    def __getattr__(self, name):
        return getattr(self.native, name)


def load_program(config):
    native_open = open

    def config_open(path, *args, **kwargs):
        if path == '/config.json':
            if config == 'missing':
                raise OSError('simulated missing configuration')
            return io.StringIO('not json' if config == 'malformed' else json.dumps(config))
        return native_open(path, *args, **kwargs)

    namespace = {'__name__': 'controller_e2e', 'open': config_open}
    exec(SOURCE, namespace)
    return namespace


def release(namespace, pins):
    for pin in pins:
        pin.deinit()
    namespace['display'].root_group = None
    namespace.clear()
    gc.collect()


def simulate(spec):
    namespace = None
    pins = []
    try:
        namespace = load_program(spec.get('config', FIXTURE))
        pins = [namespace['btn_cycle'], namespace['btn_confirm'], namespace['btn_sleep']]
        namespace['battery_bus'] = BatteryBus(spec.get('battery_samples'), spec.get('battery_busy', False))
        namespace['alarm'] = Alarm(spec.get('waking', False))
        if spec.get('retained'):
            index, previous, action = spec['retained']
            namespace['selected_index'], namespace['applied_mode'], namespace['applied_action'] = index, previous, action
            namespace['save_sleep_state']()
            namespace['selected_index'], namespace['applied_mode'], namespace['applied_action'] = 0, '--', None
            if spec.get('corrupt'):
                namespace['alarm'].sleep_memory[10] ^= 1
            if spec.get('changed_config'):
                namespace['config']['entity_id'] = 'light.different'
        namespace['display'] = Screen(namespace['display'])
        namespace['digitalio'] = Digital()
        session = Session(spec.get('outcomes', [200]))
        namespace['wifi'] = Wifi(spec.get('wifi_fail', False))
        namespace['adafruit_connection_manager'] = Manager()
        namespace['adafruit_requests'] = Requests(session)
        namespace['ssid'] = None if spec.get('missing_wifi') else 'fixture-ssid'
        namespace['password'] = 'fixture-password'
        namespace['ha_url'] = 'http://fixture-ha:8123'
        namespace['ha_token'] = '' if spec.get('missing_token') else 'fixture-token'
        clock = Clock(namespace, spec['frames'], spec.get('screenshots', False))
        session.clock = clock
        session.latency = spec.get('request_latency', 0)
        namespace['time'] = clock
        namespace['btn_sleep'] = Button(clock, 'sleep')
        namespace['btn_cycle'] = Button(clock, 'cycle')
        namespace['btn_confirm'] = Button(clock, 'confirm')
        try:
            namespace['run']()
        except (StopFrames, SleepRequested):
            pass
        assert not namespace['battery_bus'].locked, 'I2C lock leaked'
        if 'battery_reads' in spec:
            assert namespace['battery_bus'].reads == spec['battery_reads'], 'Battery refresh interval changed'
        sleeps = namespace['alarm'].calls
        assert len(sleeps) == spec.get('sleeps', 0), 'Unexpected sleep count'
        if sleeps:
            assert not namespace['wifi'].radio.enabled, 'WiFi left enabled during sleep'
            assert namespace['display'].brightness == 0, 'Backlight left on'
            assert not namespace['display'].auto_refresh, 'Display still refreshing'
            assert namespace['display'].bus.commands == [0x28, 0x10], 'Panel not put to sleep'
        expected = spec.get('posts', [])
        assert [post['body'] for post in session.posts] == expected, 'Unexpected HA request payload or duplicate requests'
        for index, post in enumerate(session.posts):
            service = spec.get('services', ['turn_on']*len(expected))[index]
            assert post['url'] == 'http://fixture-ha:8123/api/services/light/'+service, 'Wrong service endpoint'
            assert post['authorization'] == 'Bearer fixture-token', 'Missing Bearer authorization'
        assert all(response.closed for response in session.responses), 'HTTP response was not closed'
        return {'ok': True, 'name': spec['name'], 'frames': len(clock.observations), 'images': clock.images, 'sleeps': sleeps}
    except AssertionError as error:
        return {'ok': False, 'name': spec['name'], 'reason': str(error)}
    except Exception as error:
        return {'ok': False, 'name': spec['name'], 'reason': 'Unexpected '+type(error).__name__}
    finally:
        if namespace:
            release(namespace, pins)


LIVE = None


def ha_request(namespace, method, path, body=None):
    response = None
    try:
        kwargs = {'headers': {'Authorization': 'Bearer '+namespace['ha_token']}, 'timeout': 10}
        if body is not None:
            kwargs['json'] = body
        response = getattr(namespace['requests'], method)(namespace['ha_url']+path, **kwargs)
        assert response.status_code == 200, 'HA '+method.upper()+' '+path+' returned '+str(response.status_code)
        return response.json()
    finally:
        if response is not None:
            response.close()


def light_state(namespace):
    data = ha_request(namespace, 'get', '/api/states/'+namespace['entity_id'])
    attrs = data.get('attributes', {})
    keys = ('brightness', 'color_mode', 'color_temp_kelvin', 'hs_color', 'xy_color', 'rgb_color', 'rgbw_color', 'rgbww_color', 'effect')
    return {'state': data['state'], 'attributes': {key: attrs[key] for key in keys if key in attrs}}


def live_start(scene_id=None):
    global LIVE
    with open('/config.json') as file:
        config = json.load(file)
    namespace = load_program(config)
    LIVE = {'namespace': namespace, 'pins': [namespace['btn_cycle'], namespace['btn_confirm'], namespace['btn_sleep']], 'scene': None, 'index': 0, 'config': config}
    try:
        namespace['alarm'] = Alarm()
        clock = Clock(namespace, [{}])
        namespace['time'] = clock
        namespace['btn_sleep'] = Button(clock, 'sleep')
        namespace['btn_cycle'] = Button(clock, 'cycle')
        namespace['btn_confirm'] = Button(clock, 'confirm')
        try:
            namespace['run']()
        except StopFrames:
            pass
        assert namespace['wifi_ok'], 'Real WiFi connection failed'
        ha_request(namespace, 'get', '/api/')
        before = light_state(namespace)
        assert before['state'] in ('on', 'off'), 'Configured light is unavailable'
        data = ha_request(namespace, 'get', '/api/states/'+namespace['entity_id'])
        attrs = data.get('attributes', {})
        assert 'color_temp' in attrs.get('supported_color_modes', []), 'Light lacks color temperature support'
        for mode in config['modes']:
            if mode.get('action', 'on') == 'off':
                continue
            assert 0 < mode['brightness'] <= 255, 'Live presets must have nonzero brightness'
            assert attrs.get('min_color_temp_kelvin', 0) <= mode['kelvin'] <= attrs.get('max_color_temp_kelvin', 100000), 'Live preset exceeds supported Kelvin range'
        LIVE['before'] = before
        if scene_id:
            # Retain the ID even if the create request times out after reaching HA.
            LIVE['scene'] = 'scene.'+scene_id
            ha_request(namespace, 'post', '/api/services/scene/create', {'scene_id': scene_id, 'snapshot_entities': [namespace['entity_id']]})
        import os
        return {'ok': True, 'name': 'real-ha-connectivity', 'ip': str(namespace['wifi'].radio.ipv4_address), 'before': before, 'mode_count': len(config['modes']), 'scene': LIVE['scene'], 'firmware': os.uname().release}
    except AssertionError as error:
        return {'ok': False, 'name': 'real-ha-connectivity', 'reason': str(error)}
    except Exception as error:
        return {'ok': False, 'name': 'real-ha-connectivity', 'reason': 'Unexpected '+type(error).__name__}


def state_matches(actual, expected):
    if actual['state'] != expected['state']:
        return False
    if actual['state'] == 'off':
        return True
    a, e = actual['attributes'], expected['attributes']
    if 'brightness' in e and abs(a.get('brightness', -1000)-e['brightness']) > 3:
        return False
    mode = e.get('color_mode')
    if mode and a.get('color_mode') != mode:
        return False
    if mode == 'color_temp':
        return abs(a.get('color_temp_kelvin', -1000)-e['color_temp_kelvin']) <= 100
    color_key = {'hs': 'hs_color', 'xy': 'xy_color', 'rgb': 'rgb_color', 'rgbw': 'rgbw_color', 'rgbww': 'rgbww_color'}.get(mode)
    if color_key and color_key in e:
        av, ev = a.get(color_key, []), e[color_key]
        tolerance = 0.01 if mode == 'xy' else 1
        return len(av) == len(ev) and all(abs(x-y) <= tolerance for x, y in zip(av, ev))
    return True


def await_state(namespace, expected):
    import time as real_time
    deadline = real_time.monotonic()+20
    actual = None
    while real_time.monotonic() < deadline:
        actual = light_state(namespace)
        if state_matches(actual, expected):
            return actual
        real_time.sleep(0.5)
    raise AssertionError('Light did not reach expected state; observed '+json.dumps(actual))


def live_apply(index):
    namespace = LIVE['namespace']
    assert LIVE['scene'], 'A recovery snapshot is required before changing the light'
    mode = LIVE['config']['modes'][index]
    expected = {'state': 'off', 'attributes': {}} if mode.get('action', 'on') == 'off' else {'state': 'on', 'attributes': {'brightness': mode['brightness'], 'color_mode': 'color_temp', 'color_temp_kelvin': mode['kelvin']}}
    frames = [{'cycle': True} for _ in range((index-LIVE['index']) % len(LIVE['config']['modes']))]
    frames.append({'confirm': True, 'visible': ['APPLIED', str(index+1)+'/'+str(len(LIVE['config']['modes']))]})
    try:
        clock = Clock(namespace, frames)
        namespace['time'] = clock
        namespace['btn_sleep'] = Button(clock, 'sleep')
        namespace['btn_cycle'] = Button(clock, 'cycle')
        namespace['btn_confirm'] = Button(clock, 'confirm')
        try:
            namespace['run']()
        except StopFrames:
            pass
        LIVE['index'] = index
        actual = await_state(namespace, expected)
        return {'ok': True, 'name': 'real-preset-'+str(index+1), 'expected': expected, 'observed': actual}
    except AssertionError as error:
        return {'ok': False, 'name': 'real-preset-'+str(index+1), 'reason': str(error)}
    except Exception as error:
        return {'ok': False, 'name': 'real-preset-'+str(index+1), 'reason': 'Unexpected '+type(error).__name__}


def live_finish():
    global LIVE
    if LIVE is None:
        return {'ok': True, 'name': 'light-state-restored', 'detail': 'No live session opened'}
    namespace = LIVE['namespace']
    try:
        if LIVE['scene']:
            ha_request(namespace, 'post', '/api/services/scene/turn_on', {'entity_id': LIVE['scene']})
            restored = await_state(namespace, LIVE['before'])
            ha_request(namespace, 'post', '/api/services/scene/delete', {'entity_id': LIVE['scene']})
            return {'ok': True, 'name': 'light-state-restored', 'observed': restored, 'scene_deleted': True}
        return {'ok': True, 'name': 'read-only-session-closed'}
    except Exception as error:
        return {'ok': False, 'name': 'light-state-restored', 'reason': 'Restoration or cleanup failed: '+type(error).__name__, 'recovery_scene': LIVE['scene']}
    finally:
        release(namespace, LIVE['pins'])
        LIVE = None
