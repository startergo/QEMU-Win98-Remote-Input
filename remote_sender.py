#!/usr/bin/env python3
"""
Remote input sender for Linux hosts.

Reads local evdev input devices on a Linux machine and sends events
over TCP to the macOS QEMU host running the remote input server.

This is the Linux equivalent of the macOS local capture mode — it
allows you to forward input from a Linux machine (with real hardware)
to the Win98 VM running on a macOS QEMU host.

Requirements (Linux only):
  pip install evdev

Usage:
  # List available input devices:
  python3 remote_sender.py --list

  # Forward specific devices:
  python3 remote_sender.py --host 192.168.1.100 --port 9999 \
      --keyboard /dev/input/event0 --mouse /dev/input/event1

  # Auto-detect and forward all keyboards and mice:
  python3 remote_sender.py --host 192.168.1.100 --auto

  # Forward a single device (auto-detect type):
  python3 remote_sender.py --host 192.168.1.100 --device /dev/input/event2
"""

import argparse
import json
import socket
import sys
import threading
import time

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None

from keymaps import EVDEV_KEY_TO_QCODE
from network import make_key_event, make_abs_event, make_rel_event, make_btn_event, send_event


def list_devices():
    """List all available evdev input devices."""
    if not evdev:
        print("ERROR: evdev not installed. Run: pip install evdev")
        sys.exit(1)

    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    devices.sort(key=lambda d: d.path)

    print("Available input devices:\n")
    print(f"{'Path':<25} {'Name':<45} {'Type'}")
    print("-" * 90)

    for dev in devices:
        caps = dev.capabilities(verbose=False)
        types = []
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            if any(k >= ecodes.BTN_LEFT and k <= ecodes.BTN_TASK for k in keys):
                types.append("mouse")
            if any(k >= ecodes.KEY_ESC and k <= ecodes.KEY_MEDIA for k in keys):
                types.append("keyboard")
        if ecodes.EV_ABS in caps:
            types.append("touch/pen")
        if ecodes.EV_REL in caps:
            types.append("pointer")

        print(f"{dev.path:<25} {dev.name:<45} {', '.join(types) or 'other'}")

    print("\nTip: Use --keyboard and --mouse with the device path")


def detect_devices():
    """Auto-detect keyboard and mouse devices."""
    if not evdev:
        print("ERROR: evdev not installed.")
        sys.exit(1)

    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    keyboards = []
    mice = []

    for dev in devices:
        try:
            caps = dev.capabilities(verbose=False)
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                is_mouse = any(ecodes.BTN_LEFT <= k <= ecodes.BTN_TASK for k in keys)
                is_keyboard = any(ecodes.KEY_ESC <= k <= ecodes.KEY_MEDIA for k in keys)
                if is_keyboard and not is_mouse:
                    keyboards.append(dev)
                if is_mouse:
                    mice.append(dev)
        except Exception:
            pass

    return keyboards, mice


def forward_keyboard(sock, device, screen_w=32767, screen_h=32767):
    """Read keyboard events from evdev and forward over TCP."""
    print(f"[KB] Forwarding: {device.name} ({device.path})")
    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                qcode = EVDEV_KEY_TO_QCODE.get(event.code)
                if qcode:
                    down = event.value != 0  # 1=down, 0=up, 2=repeat (treat as down)
                    evt = make_key_event(qcode, down if event.value != 2 else True)
                    send_event(sock, evt)
    except Exception as e:
        print(f"[KB] Error: {e}")


def forward_mouse(sock, device, screen_w=None, screen_h=None):
    """Read mouse events from evdev and forward over TCP."""
    print(f"[MS] Forwarding: {device.name} ({device.path})")
    buttons = 0
    abs_x, abs_y = 16384, 16384

    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                if event.code == ecodes.BTN_LEFT:
                    buttons = (buttons | 1) if event.value else (buttons & ~1)
                    evt = make_btn_event("left", bool(event.value))
                    send_event(sock, evt)
                elif event.code == ecodes.BTN_MIDDLE:
                    buttons = (buttons | 4) if event.value else (buttons & ~4)
                    evt = make_btn_event("middle", bool(event.value))
                    send_event(sock, evt)
                elif event.code == ecodes.BTN_RIGHT:
                    buttons = (buttons | 2) if event.value else (buttons & ~2)
                    evt = make_btn_event("right", bool(event.value))
                    send_event(sock, evt)

            elif event.type == ecodes.EV_REL:
                # Send as relative — QEMU handles coordinate mapping
                if event.code == ecodes.REL_X:
                    evt = make_rel_event(event.value, 0)
                    send_event(sock, evt)
                elif event.code == ecodes.REL_Y:
                    evt = make_rel_event(0, event.value)
                    send_event(sock, evt)

            elif event.type == ecodes.EV_ABS:
                # Touchscreen / tablet — send as absolute
                if event.code == ecodes.ABS_X:
                    abs_x = event.value
                elif event.code == ecodes.ABS_Y:
                    abs_y = event.value
                evt = make_abs_event(abs_x, abs_y)
                send_event(sock, evt)

    except Exception as e:
        print(f"[MS] Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Forward Linux evdev input to QEMU remote input server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list
  %(prog)s --host 192.168.1.100 --keyboard /dev/input/event0 --mouse /dev/input/event1
  %(prog)s --host 192.168.1.100 --auto
        """,
    )
    parser.add_argument("--host", required=True, help="QEMU host IP address")
    parser.add_argument("--port", type=int, default=9999, help="Remote server port (default: 9999)")
    parser.add_argument("--keyboard", help="Keyboard evdev device path")
    parser.add_argument("--mouse", help="Mouse evdev device path")
    parser.add_argument("--device", help="Single device to forward (auto-detect type)")
    parser.add_argument("--auto", action="store_true", help="Auto-detect all keyboards and mice")
    parser.add_argument("--list", action="store_true", help="List available input devices")
    args = parser.parse_args()

    if not evdev:
        print("ERROR: evdev not installed. Run: pip install evdev")
        print("This script only works on Linux.")
        sys.exit(1)

    if args.list:
        list_devices()
        return

    # ── Determine devices ────────────────────────────────────
    kb_paths = []
    ms_paths = []

    if args.auto:
        keyboards, mice = detect_devices()
        kb_paths = [d.path for d in keyboards]
        ms_paths = [d.path for d in mice]
        print(f"Auto-detected: {len(kb_paths)} keyboard(s), {len(ms_paths)} mouse/mice")
    else:
        if args.keyboard:
            kb_paths.append(args.keyboard)
        if args.mouse:
            ms_paths.append(args.mouse)
        if args.device:
            # Auto-detect type
            dev = evdev.InputDevice(args.device)
            caps = dev.capabilities(verbose=False)
            keys = caps.get(ecodes.EV_KEY, [])
            is_mouse = any(ecodes.BTN_LEFT <= k <= ecodes.BTN_TASK for k in keys)
            if is_mouse:
                ms_paths.append(args.device)
            else:
                kb_paths.append(args.device)

    if not kb_paths and not ms_paths:
        print("No devices specified. Use --keyboard, --mouse, --device, or --auto")
        sys.exit(1)

    # ── Connect to remote server ─────────────────────────────
    print(f"Connecting to {args.host}:{args.port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
    except ConnectionRefusedError:
        print(f"ERROR: Connection refused. Is the remote server running?")
        print(f"  On the macOS host: python3 main.py --qmp /tmp/qemu.sock --remote --port {args.port}")
        sys.exit(1)

    print(f"Connected to {args.host}:{args.port}")

    # ── Forward devices ──────────────────────────────────────
    threads = []

    for path in kb_paths:
        dev = evdev.InputDevice(path)
        t = threading.Thread(target=forward_keyboard, args=(sock, dev), daemon=True)
        t.start()
        threads.append(t)

    for path in ms_paths:
        dev = evdev.InputDevice(path)
        t = threading.Thread(target=forward_mouse, args=(sock, dev), daemon=True)
        t.start()
        threads.append(t)

    print(f"Forwarding {len(threads)} device(s). Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
