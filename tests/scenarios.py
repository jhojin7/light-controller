"""Black-box input traces and independently specified expected outcomes."""
from copy import deepcopy

DAY = {'entity_id': 'light.e2e_fixture', 'brightness': 255, 'color_temp_kelvin': 5000}
EVENING = {'entity_id': 'light.e2e_fixture', 'brightness': 128, 'color_temp_kelvin': 2700}
SLEEP = {'entity_id': 'light.e2e_fixture', 'brightness': 25, 'color_temp_kelvin': 2200}


def scenarios(fixture, screenshots=False):
    navigation = [
        {'visible': ['DAY', '100%', '5000K', '1/3', 'D2 TO APPLY', 'ON: --'], 'absent': ['EVENING', 'SLEEP']},
        {'cycle': True, 'visible': ['EVENING', '50%', '2700K', '2/3'], 'absent': ['DAY', 'SLEEP']},
        {'cycle': True, 'visible': ['SLEEP', '9%', '2200K', '3/3'], 'absent': ['DAY', 'EVENING']},
        {'cycle': True, 'visible': ['DAY', '1/3']},
    ]
    cases = [
        {'name': 'startup-and-navigation', 'frames': navigation, 'screenshots': screenshots},
        {'name': 'apply-all-presets', 'frames': [
            {'confirm': True, 'visible': ['APPLIED', 'ON: DAY']},
            {'cycle': True, 'visible': ['EVENING', 'ON: DAY', 'D2 TO APPLY']},
            {'confirm': True, 'visible': ['APPLIED', 'ON: EVENING']},
            {'cycle': True, 'visible': ['SLEEP', 'ON: EVENING']},
            {'confirm': True, 'visible': ['APPLIED', 'ON: SLEEP']},
        ], 'posts': [DAY, EVENING, SLEEP]},
        {'name': 'button-debounce-and-hold-repeat', 'frames': [
            {'time': 0.29, 'cycle': True, 'visible': ['DAY', '1/3']},
            {'time': 0.30, 'cycle': True, 'visible': ['DAY', '1/3']},
            {'time': 0.31, 'cycle': True, 'visible': ['EVENING', '2/3']},
            {'time': 0.40, 'cycle': True, 'visible': ['EVENING', '2/3']},
            {'time': 0.62, 'cycle': True, 'visible': ['SLEEP', '3/3']},
        ]},
        {'name': 'confirm-debounce', 'frames': [
            {'time': 0.31, 'confirm': True, 'visible': ['APPLIED']},
            {'time': 0.40, 'confirm': True, 'visible': ['APPLIED']},
        ], 'posts': [DAY]},
        {'name': 'simultaneous-buttons-cycle-before-apply', 'frames': [
            {'cycle': True, 'confirm': True, 'visible': ['EVENING', '2/3', 'ON: EVENING', 'APPLIED']},
        ], 'posts': [EVENING]},
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


def sleep_scenarios():
    return [
        {'name': 'idle-sleeps-at-fifteen-seconds', 'frames': [
            {'time': 0}, {'time': 14.99}, {'time': 15},
        ], 'sleeps': 1},
        {'name': 'activity-resets-idle', 'frames': [
            {'time': 0}, {'time': 14, 'cycle': True, 'visible': ['EVENING']},
            {'time': 14.1}, {'time': 28.99}, {'time': 29},
        ], 'sleeps': 1},
        {'name': 'd0-short-press-does-not-sleep', 'frames': [
            {'time': 0}, {'time': 1, 'sleep': True}, {'time': 1.99, 'sleep': True},
            {'time': 2}, {'time': 2.1},
        ]},
        {'name': 'd0-hold-waits-for-all-buttons-release', 'frames': [
            {'time': 0}, {'time': 1, 'sleep': True, 'cycle': True, 'confirm': True},
            {'time': 2, 'sleep': True, 'visible': ['RELEASE TO SLEEP', 'DAY']},
            {'time': 3, 'confirm': True}, {'time': 4}, {'time': 4.1},
        ], 'sleeps': 1},
        {'name': 'wake-confirm-is-consumed', 'waking': True, 'frames': [
            {'time': 0.5, 'confirm': True}, {'time': 1, 'confirm': True},
            {'time': 1.5}, {'time': 1.6}, {'time': 2, 'confirm': True},
        ], 'posts': [DAY]},
        {'name': 'wake-cycle-is-consumed', 'waking': True, 'frames': [
            {'time': 0.5, 'cycle': True, 'visible': ['DAY']},
            {'time': 1, 'cycle': True, 'visible': ['DAY']},
            {'time': 1.5}, {'time': 1.6},
            {'time': 2, 'cycle': True, 'visible': ['EVENING']},
        ]},
        {'name': 'wake-bounce-is-consumed', 'waking': True, 'frames': [
            {'time': 0.5, 'confirm': True}, {'time': 0.6},
            {'time': 0.62, 'confirm': True}, {'time': 0.8}, {'time': 0.86},
        ]},
        {'name': 'wake-restores-selection-and-history', 'waking': True,
         'retained': [1, 'DAY', 'on'], 'frames': [
             {'visible': ['EVENING', 'ON: DAY']}, {}, {},
         ]},
        {'name': 'corrupt-retention-is-rejected', 'waking': True,
         'retained': [1, 'DAY', 'on'], 'corrupt': True, 'frames': [
             {'visible': ['DAY', 'ON: --']},
         ]},
        {'name': 'changed-config-clears-retention', 'waking': True,
         'retained': [1, 'DAY', 'on'], 'changed_config': True, 'frames': [
             {'visible': ['DAY', 'ON: --']},
         ]},
        {'name': 'invalid-selection-clears-retention', 'waking': True, 'retained': [999, 'DAY', 'on'], 'frames': [{'visible': ['DAY', 'ON: --']}]},
        {'name': 'invalid-history-clears-retention', 'waking': True, 'retained': [1, 'DAY', 'off'], 'frames': [{'visible': ['DAY', 'ON: --']}]},
        {'name': 'reset-clears-retention', 'retained': [1, 'DAY', 'on'], 'frames': [
            {'visible': ['DAY', 'ON: --']},
        ]},
        {'name': 'wifi-failure-still-sleeps', 'wifi_fail': True, 'frames': [
            {'time': 0, 'visible': ['WIFI FAIL']}, {'time': 15},
        ], 'sleeps': 1},
        {'name': 'apply-at-idle-boundary-resets-window', 'frames': [
            {'time': 0}, {'time': 15, 'confirm': True, 'visible': ['APPLIED']},
            {'time': 15.1}, {'time': 29.99}, {'time': 30},
        ], 'posts': [DAY], 'sleeps': 1},
        {'name': 'failed-request-still-sleeps', 'outcomes': [500], 'frames': [
            {'time': 0}, {'time': 1, 'confirm': True, 'visible': ['ERR 500']},
            {'time': 1.1}, {'time': 15.99}, {'time': 16},
        ], 'posts': [DAY], 'sleeps': 1},
    ]



def battery_scenarios():
    return [
        {'name': 'battery-percent-and-refresh', 'battery_samples': [0x4980, 0x1400], 'battery_reads': 2, 'frames': [
            {'time': 0, 'visible': ['73%']},
            {'time': 14, 'cycle': True, 'visible': ['73%']},
            {'time': 14.99, 'visible': ['73%']},
            {'time': 15, 'visible': ['20%']},
        ]},
        {'name': 'battery-clamps-full', 'battery_samples': [0x65ff], 'frames': [{'visible': ['100%']}]},
        {'name': 'battery-empty', 'battery_samples': [0], 'frames': [{'visible': ['0%']}]},
        {'name': 'battery-gauge-failure-is-nonfatal', 'battery_samples': ['fail'], 'frames': [
            {'time': 0, 'visible': ['--%']}, {'time': 15},
        ], 'sleeps': 1},
        {'name': 'battery-bus-busy-is-nonfatal', 'battery_busy': True, 'frames': [
            {'visible': ['--%']}, {'confirm': True, 'visible': ['APPLIED']},
        ], 'posts': [DAY]},
        {'name': 'battery-gauge-recovers', 'battery_samples': ['fail', 0x3200], 'frames': [
            {'time': 0, 'visible': ['--%']}, {'time': 14, 'cycle': True},
            {'time': 15, 'visible': ['50%']},
        ]},
    ]
