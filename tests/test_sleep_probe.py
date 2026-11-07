"""Keep the hardware idle observer capable of detecting unsolicited wakes."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from e2e_sleep import instrument_idle


class IdleProbeTests(unittest.TestCase):
    def test_missing_boot_observation_fails_closed(self):
        source = (ROOT / 'code.py').read_text().replace('import os\n', 'import os as os\n', 1)
        with self.assertRaisesRegex(AssertionError, 'Boot observation'):
            instrument_idle(source)

    def test_idle_observer_adds_neither_button_simulation_nor_wake_timer(self):
        source = (ROOT / 'code.py').read_text()
        probe = instrument_idle(source)
        ast.parse(probe)
        self.assertIn('if __name__ == "__main__":\n    run()', probe)
        calls = [node for node in ast.walk(ast.parse(probe)) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(call.func, ast.Attribute) and call.func.attr == 'TimeAlarm'
                             for call in calls))
        self.assertNotIn('class ProbeButton', probe)
        self.assertIn("'event': 'boot'", probe)
        self.assertIn("'event': 'idle-shutdown'", probe)
