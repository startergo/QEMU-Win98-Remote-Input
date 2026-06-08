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
                needs_shift = ch in _SHIFT_CHARS
                if needs_shift:
                    self.send_key("shift", down=True)
                self.send_key(qcode, down=True)
                self.send_key(qcode, down=False)
                if needs_shift:
                    self.send_key("shift", down=False)
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
            count = min(abs(dy), 3)
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

    # ── Display / Recovery helpers ─────────────────────────

    def screenshot(self, path):
        """Capture VM display to a PNG file via QMP screendump.

        Uses PNG format directly on QEMU >= 7.0.  Falls back to PPM -> PNG
        conversion via Pillow on older versions.  Raises on empty output
        (which indicates a silently failed screendump).
        """
        import os
        path = str(path)

        # Try native PNG (QEMU >= 7.0); catch QMPError for older QEMU
        # that doesn't support the "format" parameter.
        try:
            self._execute("screendump", {"filename": path, "format": "png"})
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return
        except QMPError:
            pass  # Fall through to PPM conversion

        # Fallback: PPM -> PNG conversion
        import tempfile
        from PIL import Image
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as tmp:
            tmp_name = tmp.name
        try:
            self._execute("screendump", {"filename": tmp_name})
            if os.path.getsize(tmp_name) == 0:
                raise RuntimeError("screendump returned empty file")
            with Image.open(tmp_name) as img:
                img.save(path, format="png")
        finally:
            os.unlink(tmp_name)

    def press_enter(self):
        """Send an Enter key press and release."""
        self.send_key("ret", down=True)
        self.send_key("ret", down=False)

    def navigate_menu(self, *keys):
        """Navigate macOS menu bar via single-character menu shortcuts.

        Activates the menu bar (Ctrl+F2), then types each key + Enter to
        drill through submenus.  For example:
            navigate_menu('u', 't')   -> Utilities -> Terminal
        """
        self.send_key_combo(["ctrl", "f2"])
        time.sleep(0.3)
        for key in keys:
            self.type_string(key, delay=0.05)
            time.sleep(0.3)
            self.press_enter()
            time.sleep(0.3)

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


# Characters that need Shift held during press.
_SHIFT_CHARS = set('!@#$%^&*()_+{}|:"~<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ')

# Maps any printable ASCII character to its base qcode (the key without shift).
# Shifted symbols map to the key that produces them when shifted.
_BASE_KEY = {
    **{c: c for c in 'abcdefghijklmnopqrstuvwxyz0123456789'},
    **{c.upper(): c for c in 'abcdefghijklmnopqrstuvwxyz'},
    ' ': 'spc', '\n': 'ret', '\t': 'tab',
    '.': 'dot', ',': 'comma', '/': 'slash', '\\': 'backslash',
    ';': 'semicolon', "'": 'apostrophe', '[': 'bracket_left',
    ']': 'bracket_right', '-': 'minus', '=': 'equal',
    '`': 'grave_accent',
    # Shifted symbols -> base key
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
    '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': 'minus', '+': 'equal',
    '{': 'bracket_left', '}': 'bracket_right',
    ':': 'semicolon', '"': 'apostrophe',
    '~': 'grave_accent', '|': 'backslash',
    '<': 'comma', '>': 'dot', '?': 'slash',
}


def _char_to_qcode(ch):
    return _BASE_KEY.get(ch)
