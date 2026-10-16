"""Exercise the real serial transport against an external pseudo-terminal peer."""
import os
import pty
import select
import threading
import unittest

from scripts.board_serial import Board


class Peer:
    def __enter__(self):
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.stop = threading.Event()
        self.reboots = 0
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def run(self):
        raw, running, code = False, False, bytearray()
        while not self.stop.is_set():
            if not select.select([self.master], [], [], 0.05)[0]:
                continue
            try:
                data = os.read(self.master, 4096)
                for byte in data:
                    if byte == 2:
                        raw, running = False, False
                        code.clear()
                        os.write(self.master, b'\r\n>>> ')
                    elif byte == 3:
                        code.clear()
                        if raw and running:
                            os.write(self.master, b'\x04KeyboardInterrupt\x04>')
                            running = False
                        elif raw:
                            os.write(self.master, b'>')
                        else:
                            os.write(self.master, b'\r\n>>> ')
                    elif byte == 1:
                        raw = True
                        code.clear()
                        os.write(self.master, b'raw REPL; CTRL-B to exit\r\n>')
                    elif byte == 4:
                        if not raw:
                            self.reboots += 1
                            os.write(self.master, b'soft reboot\r\n')
                        else:
                            text = bytes(code)
                            code.clear()
                            if text == b'hang':
                                running = True
                                os.write(self.master, b'OK')
                            elif text == b'fail':
                                os.write(self.master, b'OK\x04private-token-must-not-escape\x04>')
                            elif b'__E2E__' in text:
                                os.write(self.master, b'OK__E2E__{"ok": true}\r\n\x04\x04>')
                            else:
                                os.write(self.master, b'OKhello\r\n\x04\x04>')
                    elif raw:
                        code.append(byte)
                    elif byte == 13:
                        os.write(self.master, b'>>> ')
            except OSError:
                return

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=1)
        os.close(self.master)
        os.close(self.slave)


class SerialTransportTests(unittest.TestCase):
    def test_rpc_and_controller_restart(self):
        with Peer() as peer:
            with Board(peer.path) as board:
                self.assertEqual(board.execute('anything'), 'hello\r\n')
                self.assertEqual(board.rpc("{'ok': True}"), {'ok': True})
            self.assertEqual(peer.reboots, 1)

    def test_timeout_can_be_cancelled_before_recovery_rpc(self):
        with Peer() as peer:
            with Board(peer.path) as board:
                with self.assertRaises(TimeoutError):
                    board.execute('hang', timeout=0.1)
                board.cancel_pending()
                self.assertTrue(board.rpc("{'ok': True}")['ok'])
            self.assertEqual(peer.reboots, 1)

    def test_board_tracebacks_do_not_leak_private_output(self):
        with Peer() as peer:
            with Board(peer.path) as board:
                with self.assertRaises(RuntimeError) as error:
                    board.execute('fail')
                self.assertNotIn('private-token', str(error.exception))
            self.assertEqual(peer.reboots, 1)
