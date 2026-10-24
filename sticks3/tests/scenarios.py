"""Black-box input traces and independently specified expected outcomes."""
from copy import deepcopy

DAY = {'entity_id': 'light.e2e_fixture', 'brightness': 255, 'color_temp_kelvin': 5000}
EVENING = {'entity_id': 'light.e2e_fixture', 'brightness': 128, 'color_temp_kelvin': 2700}
SLEEP = {'entity_id': 'light.e2e_fixture', 'brightness': 25, 'color_temp_kelvin': 2200}


def scenarios(fixture, screenshots=False):
    navigation = [
        {'visible': ['DAY', '100%', '5000K', '1/3', 'HOLD A TO SET', 'ON: --'], 'absent': ['EVENING', 'SLEEP']},
        {'cycle': True, 'visible': ['EVENING', '50%', '2700K', '2/3'], 'absent': ['DAY', 'SLEEP']},
        {'cycle': True, 'visible': ['SLEEP', '9%', '2200K', '3/3'], 'absent': ['DAY', 'EVENING']},
        {'cycle': True, 'visible': ['DAY', '1/3']},
    ]
    cases = [
        {'name': 'startup-and-navigation', 'frames': navigation, 'screenshots': screenshots},
        {'name': 'apply-all-presets', 'frames': [
            {'confirm': True, 'visible': ['APPLIED', 'ON: DAY']},
            {'cycle': True, 'visible': ['EVENING', 'ON: DAY', 'HOLD A TO SET']},
            {'confirm': True, 'visible': ['APPLIED', 'ON: EVENING']},
            {'cycle': True, 'visible': ['SLEEP', 'ON: EVENING']},
            {'confirm': True, 'visible': ['APPLIED', 'ON: SLEEP']},
        ], 'posts': [DAY, EVENING, SLEEP]},
        {'name': 'success-201', 'outcomes': [201], 'frames': [
            {'confirm': True, 'visible': ['APPLIED', 'ON: DAY']},
        ], 'posts': [DAY]},
        {'name': 'missing-wifi', 'missing_wifi': True, 'frames': [
            {'visible': ['WIFI FAIL', 'ON: --']},
            {'confirm': True, 'visible': ['ON: --'], 'absent': ['APPLIED']},
        ]},
        {'name': 'failed-wifi', 'wifi_fail': True, 'frames': [
            {'visible': ['WIFI FAIL', 'ON: --']},
        ]},
        {'name': 'missing-token', 'missing_token': True, 'frames': [
            {'confirm': True, 'visible': ['NO TOKEN', 'ON: --'], 'absent': ['APPLIED']},
        ]},
        {'name': 'missing-config-fallback', 'config': 'missing', 'frames': [
            {'visible': ['DAY', '100%', '5000K', '1/4']},
        ]},
        {'name': 'malformed-config-fallback', 'config': 'malformed', 'frames': [
            {'visible': ['DAY', '100%', '5000K', '1/4']},
        ]},
        {'name': 'empty-config-error-card', 'config': {'modes': []}, 'frames': [
            {'visible': ['ERROR', '0%', '0K', '1/1']},
        ]},
    ]
    for outcome, visible in ((401, 'ERR 401'), (500, 'ERR 500'), ('raise', 'FAILED')):
        cases.append({'name': 'request-failure-'+str(outcome), 'outcomes': [200, outcome], 'frames': [
            {'confirm': True, 'visible': ['APPLIED', 'ON: DAY']},
            {'cycle': True, 'visible': ['EVENING', 'ON: DAY']},
            {'confirm': True, 'visible': [visible, 'ON: DAY'], 'absent': ['APPLIED', 'ON: EVENING']},
        ], 'posts': [DAY, EVENING]})
    single = deepcopy(fixture)
    single['modes'] = single['modes'][:1]
    cases.append({'name': 'single-mode-wrap', 'config': single, 'frames': [
        {'visible': ['DAY', '1/1']}, {'cycle': True, 'visible': ['DAY', '1/1']},
    ]})
    seven = deepcopy(fixture)
    seven['modes'] += [
        {'name': 'EXTREMELY LONG MODE NAME', 'brightness': 0, 'kelvin': 10000},
        {'name': 'ZERO', 'brightness': 0, 'kelvin': 2200},
        {'name': 'CUSTOM', 'brightness': 255, 'kelvin': 6500, 'icon': 'moon'},
        {'name': 'UNKNOWN', 'brightness': 128, 'kelvin': 2500},
    ]
    names = ['DAY', 'EVENING', 'SLEEP', 'EXTREME...', 'ZERO', 'CUSTOM', 'UNKNOWN', 'DAY']
    pages = ['1/7', '2/7', '3/7', '4/7', '5/7', '6/7', '7/7', '1/7']
    cases.append({'name': 'seven-modes-and-long-names', 'config': seven, 'frames': [
        {'cycle': index > 0, 'visible': [name, pages[index]]}
        for index, name in enumerate(names)
    ]})
    return cases


def off_scenarios(fixture):
    config = deepcopy(fixture)
    config['modes'].append({'name': 'OFF', 'action': 'off'})
    off_request = {'entity_id': 'light.e2e_fixture'}
    return [
        {'name': 'off-and-back-on', 'config': config, 'frames': [
            {'visible': ['DAY', '1/4']},
            {'cycle': True, 'visible': ['EVENING', '2/4']},
            {'cycle': True, 'visible': ['SLEEP', '3/4']},
            {'cycle': True, 'visible': ['OFF', '0%', '--', '4/4']},
            {'confirm': True, 'visible': ['APPLIED', 'LIGHT OFF']},
            {'cycle': True, 'visible': ['DAY', '1/4', 'LIGHT OFF']},
            {'confirm': True, 'visible': ['APPLIED', 'ON: DAY'], 'absent': ['LIGHT OFF']},
        ], 'posts': [off_request, DAY], 'services': ['turn_off', 'turn_on']},
        {'name': 'failed-off-preserves-last-applied', 'config': config, 'outcomes': [200, 500], 'frames': [
            {'confirm': True, 'visible': ['ON: DAY', 'APPLIED']},
            {'cycle': True}, {'cycle': True}, {'cycle': True, 'visible': ['OFF']},
            {'confirm': True, 'visible': ['ERR 500', 'ON: DAY'], 'absent': ['LIGHT OFF', 'APPLIED']},
        ], 'posts': [DAY, off_request], 'services': ['turn_on', 'turn_off']},
    ]
