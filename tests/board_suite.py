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
        pins = [namespace['btn_cycle'], namespace['btn_confirm']]
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
    def __init__(self, fail=False):
        self.fail = fail

    def connect(self, *_):
        if self.fail:
            raise OSError('simulated network failure')


class Wifi:
    def __init__(self, fail=False):
        self.radio = Radio(fail)


class Manager:
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

    def post(self, url, json, headers, timeout):
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

    def monotonic(self):
        return self.frames[self.index].get('time', (self.index+1)*0.5)

    def sleep(self, _):
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

    @property
    def value(self):
        return self.clock.frames[self.clock.index].get(self.key, False)


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
        pins = [namespace['btn_cycle'], namespace['btn_confirm']]
        session = Session(spec.get('outcomes', [200]))
        namespace['wifi'] = Wifi(spec.get('wifi_fail', False))
        namespace['adafruit_connection_manager'] = Manager()
        namespace['adafruit_requests'] = Requests(session)
        namespace['ssid'] = None if spec.get('missing_wifi') else 'fixture-ssid'
        namespace['password'] = 'fixture-password'
        namespace['ha_url'] = 'http://fixture-ha:8123'
        namespace['ha_token'] = '' if spec.get('missing_token') else 'fixture-token'
        clock = Clock(namespace, spec['frames'], spec.get('screenshots', False))
        namespace['time'] = clock
        namespace['btn_cycle'] = Button(clock, 'cycle')
        namespace['btn_confirm'] = Button(clock, 'confirm')
        try:
            namespace['run']()
        except StopFrames:
            pass
        expected = spec.get('posts', [])
        assert [post['body'] for post in session.posts] == expected, 'Unexpected HA request payload or duplicate requests'
        for index, post in enumerate(session.posts):
            service = spec.get('services', ['turn_on']*len(expected))[index]
            assert post['url'] == 'http://fixture-ha:8123/api/services/light/'+service, 'Wrong service endpoint'
            assert post['authorization'] == 'Bearer fixture-token', 'Missing Bearer authorization'
        assert all(response.closed for response in session.responses), 'HTTP response was not closed'
        return {'ok': True, 'name': spec['name'], 'frames': len(clock.observations), 'images': clock.images}
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
    LIVE = {'namespace': namespace, 'pins': [namespace['btn_cycle'], namespace['btn_confirm']], 'scene': None, 'index': 0, 'config': config}
    try:
        clock = Clock(namespace, [{}])
        namespace['time'] = clock
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
