"""
Network protocol for remote input forwarding.

Supports two modes:
  1. Server: Listens for incoming input events over TCP and forwards to QEMU.
  2. Client (Linux): Reads local evdev devices and sends events over TCP.

Protocol: newline-delimited JSON lines, one event per line.

Event formats:
  {"type": "key",     "key": "a",       "down": true}
  {"type": "abs",     "x": 16384,       "y": 8192}
  {"type": "rel",     "dx": 10,         "dy": -5}
  {"type": "btn",     "button": "left", "down": true}
  {"type": "scroll",  "dy": 3,          "dx": 0}
"""

import json
import socket
import sys
import time

from qmp_client import QMPClient


# ── Server (runs on the QEMU host) ────────────────────────────

def start_server(qmp, host="0.0.0.0", port=9999):
    """
    Listen for remote input events over TCP and forward to QEMU.

    This is the QEMU-host-side server. It accepts connections from
    remote sender clients and translates JSON events into QMP commands.

    Args:
        qmp: Connected QMPClient instance.
        host: Bind address (default: all interfaces).
        port: Listen port (default: 9999).
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)

    print(f"Remote input server listening on {host}:{port}")
    print("Waiting for connections... (Ctrl+C to stop)")

    try:
        while True:
            conn, addr = server.accept()
            print(f"[+] Client connected: {addr[0]}:{addr[1]}")
            threading_handler(conn, addr, qmp)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.close()


def threading_handler(conn, addr, qmp):
    """Handle a single client connection."""
    import threading
    t = threading.Thread(target=_handle_client, args=(conn, addr, qmp), daemon=True)
    t.start()


def _handle_client(conn, addr, qmp):
    """Process incoming JSON events from a remote sender."""
    buf = b""
    stats = {"events": 0, "errors": 0}

    try:
        while True:
            data = conn.recv(8192)
            if not data:
                break
            buf += data

            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    _dispatch_event(qmp, evt)
                    stats["events"] += 1
                except (json.JSONDecodeError, KeyError) as e:
                    stats["errors"] += 1

    except ConnectionResetError:
        pass
    except OSError:
        pass
    finally:
        conn.close()
        print(f"[-] Client disconnected: {addr[0]}:{addr[1]} "
              f"({stats['events']} events, {stats['errors']} errors)")


def _dispatch_event(qmp, evt):
    """Route a single JSON event to the appropriate QMP method."""
    evt_type = evt["type"]

    if evt_type == "key":
        qmp.send_key(evt["key"], evt["down"])

    elif evt_type == "abs":
        qmp.send_mouse_abs(evt["x"], evt["y"])

    elif evt_type == "rel":
        qmp.send_mouse_rel(evt["dx"], evt["dy"])

    elif evt_type == "btn":
        qmp.send_mouse_btn(evt["button"], evt["down"])

    elif evt_type == "scroll":
        qmp.send_scroll(evt.get("dy", 0), evt.get("dx", 0))

    else:
        raise KeyError(f"Unknown event type: {evt_type}")


# ── Helpers for building events ───────────────────────────────

def make_key_event(key, down):
    """Create a keyboard event dict."""
    return {"type": "key", "key": key, "down": down}


def make_abs_event(x, y):
    """Create an absolute mouse event dict."""
    return {"type": "abs", "x": x, "y": y}


def make_rel_event(dx, dy):
    """Create a relative mouse event dict."""
    return {"type": "rel", "dx": dx, "dy": dy}


def make_btn_event(button, down):
    """Create a mouse button event dict."""
    return {"type": "btn", "button": button, "down": down}


def make_scroll_event(dy, dx=0):
    """Create a scroll wheel event dict."""
    return {"type": "scroll", "dy": dy, "dx": dx}


def send_event(sock, event):
    """Send a single event as a JSON line."""
    sock.sendall((json.dumps(event) + "\n").encode())
