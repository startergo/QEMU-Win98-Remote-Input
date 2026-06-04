"""
QMP (QEMU Machine Protocol) client for sending input events.

Provides a simple interface for injecting keyboard, mouse, and touch
events into a running QEMU instance. Works with any QEMU guest OS
including Windows 98, DOS, etc.
"""

import json
import socket
import time


class QMPError(Exception):
    """Raised when QMP returns an error."""


class QMPClient:
    """
    Minimal QMP client for input event injection.

    Connects to a QEMU instance via Unix socket and sends input events
    using the input-send-event command. Requires QEMU to be started with:
        -qmp unix:/path/to/qemu.sock,server,nowait

    Usage:
        qmp = QMPClient("/tmp/qemu.sock")
        qmp.send_key("a", down=True)
        qmp.send_key("a", down=False)
        qmp.send_mouse_abs(16384, 16384)
        qmp.disconnect()
    """

    def __init__(self, sock_path, timeout=5):
        self.sock_path = sock_path
        self._buf = b""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(sock_path)

        greeting = self._read_response()
        if "QMP" not in greeting:
            raise QMPError(f"Invalid QMP greeting: {greeting}")

        self._execute("qmp_capabilities")

    def _read_response(self):
        while True:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                raise QMPError("QMP read timed out")
            if not chunk:
                raise QMPError("QMP connection closed")
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
        return {}

    def _execute(self, command, arguments=None):
        msg = {"execute": command}
        if arguments:
            msg["arguments"] = arguments
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        resp = self._read_response()
        if "error" in resp:
            raise QMPError(f"QMP error: {resp['error']}")
        return resp.get("return", {})

    # ── Keyboard ────────────────────────────────────────────

    def send_key(self, qcode, down=True):
        self._execute("input-send-event", {
            "events": [{"type": "key", "data": {"key": {"type": "qcode", "data": qcode}, "down": down}}]
        })

    def send_key_combo(self, qcodes):
        for qcode in qcodes:
            self.send_key(qcode, down=True)
        for qcode in reversed(qcodes):
            self.send_key(qcode, down=False)

    def type_string(self, text, delay=0.03):
        for ch in text:
            qcode = _char_to_qcode(ch)
            if qcode:
                if ch.isupper():
                    self.send_key("shift", down=True)
                    self.send_key(qcode, down=True)
                    self.send_key(qcode, down=False)
                    self.send_key("shift", down=False)
                else:
                    self.send_key(qcode, down=True)
                    self.send_key(qcode, down=False)
                time.sleep(delay)

    # ── Mouse ───────────────────────────────────────────────

    def send_mouse_abs(self, x, y):
        self._execute("input-send-event", {
            "events": [{"type": "abs", "data": {"x": int(x), "y": int(y)}}]
        })

    def send_mouse_rel(self, dx, dy):
        self._execute("input-send-event", {
            "events": [
                {"type": "rel", "data": {"axis": "x", "value": int(dx)}},
                {"type": "rel", "data": {"axis": "y", "value": int(dy)}},
            ]
        })

    def send_mouse_btn(self, button, down):
        self._execute("input-send-event", {
            "events": [{"type": "btn", "data": {"button": button, "down": down}}]
        })

    def send_scroll(self, dy, dx=0, keys="arrows"):
        """Send scroll as keyboard key presses.

        Args:
            dy: Vertical scroll units. Positive = scroll up, negative = scroll down.
            dx: Ignored.
            keys: "arrows" for Arrow Up/Down (Explorer, text editors),
                  "space" for Space/Shift+Space (web browsers).
        """
        count = min(abs(dy), 3)
        if keys == "space":
            # Space scrolls a full page — one press per event is enough
            if dy > 0:
                self.send_key("shift", down=True)
                self.send_key("spc", down=True)
                self.send_key("spc", down=False)
                self.send_key("shift", down=False)
            elif dy < 0:
                self.send_key("spc", down=True)
                self.send_key("spc", down=False)
        else:
            key = "up" if dy > 0 else "down"
            for _ in range(count):
                self.send_key(key, down=True)
                self.send_key(key, down=False)

    def click(self, x, y, button="left"):
        self.send_mouse_abs(x, y)
        time.sleep(0.01)
        self.send_mouse_btn(button, True)
        time.sleep(0.01)
        self.send_mouse_btn(button, False)

    # ── Connection ──────────────────────────────────────────

    def disconnect(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sock.close()


def _char_to_qcode(ch):
    _map = {
        'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd', 'e': 'e',
        'f': 'f', 'g': 'g', 'h': 'h', 'i': 'i', 'j': 'j',
        'k': 'k', 'l': 'l', 'm': 'm', 'n': 'n', 'o': 'o',
        'p': 'p', 'q': 'q', 'r': 'r', 's': 's', 't': 't',
        'u': 'u', 'v': 'v', 'w': 'w', 'x': 'x', 'y': 'y',
        'z': 'z',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
        ' ': 'spc', '\n': 'ret', '\t': 'tab',
        '.': 'dot', ',': 'comma', '/': 'slash', '\\': 'backslash',
        ';': 'semicolon', "'": 'apostrophe', '[': 'bracket_left',
        ']': 'bracket_right', '-': 'minus', '=': 'equal',
        '`': 'grave_accent',
    }
    return _map.get(ch.lower())
