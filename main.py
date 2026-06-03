#!/usr/bin/env python3
"""
QEMU Win98 Remote Input — Main CLI

Forward host input events into a QEMU Windows 98 guest via QMP.
macOS equivalent of remote-evdev-python that works with any guest OS.

Modes:
  local    Capture macOS input via CGEvent and forward to QEMU (default)
  remote   Listen for TCP input events and forward to QEMU
  inject   One-shot injection for testing (e.g. type text, click coordinates)

Usage:
  # Mirror host input to guest (non-intrusive):
  python3 main.py --qmp /tmp/qemu-win98.sock

  # Capture host input exclusively for guest:
  python3 main.py --qmp /tmp/qemu-win98.sock --capture

  # Remote mode (listen for network events):
  python3 main.py --qmp /tmp/qemu-win98.sock --remote --port 9999

  # One-shot injection:
  python3 main.py --qmp /tmp/qemu-win98.sock --inject --type "Hello Win98"
  python3 main.py --qmp /tmp/qemu-win98.sock --inject --click 16384,8192
  python3 main.py --qmp /tmp/qemu-win98.sock --inject --key combo ctrl alt delete
"""

import argparse
import sys
import time

from qmp_client import QMPClient, QMPError


def cmd_local(args):
    """Local mode: capture macOS input and forward to QEMU."""
    if args.app:
        from app import run_app
        qmp = QMPClient(args.qmp)
        print(f"Connected to QEMU at {args.qmp}")
        run_app(qmp, scroll_keys=args.scroll_keys)
        return
    from macos_input import start_capture
    qmp = QMPClient(args.qmp)
    print(f"Connected to QEMU at {args.qmp}")
    start_capture(qmp, capture=args.capture, scroll_only=args.scroll_only,
                  scroll_keys=args.scroll_keys)


def cmd_remote(args):
    """Remote mode: listen for network input events."""
    from network import start_server
    qmp = QMPClient(args.qmp)
    print(f"Connected to QEMU at {args.qmp}")
    start_server(qmp, host=args.listen, port=args.port)


def cmd_inject(args):
    """Inject mode: one-shot input injection for testing."""
    qmp = QMPClient(args.qmp)
    print(f"Connected to QEMU at {args.qmp}")

    try:
        if args.type_text:
            print(f"Typing: {args.type_text!r}")
            qmp.type_string(args.type_text, delay=args.delay / 1000.0)
            print("Done.")

        elif args.click:
            x, y = args.click
            print(f"Clicking at ({x}, {y})")
            qmp.click(x, y)
            print("Done.")

        elif args.key:
            keys = args.key
            if keys[0] == "combo":
                print(f"Key combo: {'+'.join(keys[1:])}")
                qmp.send_key_combo(keys[1:])
            else:
                for k in keys:
                    print(f"Key: {k}")
                    qmp.send_key(k, down=True)
                    time.sleep(0.02)
                    qmp.send_key(k, down=False)
            print("Done.")

        elif args.move:
            x, y = args.move
            print(f"Moving to ({x}, {y})")
            qmp.send_mouse_abs(x, y)
            print("Done.")

        else:
            print("No injection action specified. Use --type, --click, --key, or --move")
            print("Example: python3 main.py --qmp /tmp/qemu.sock --inject --key a b c")
            sys.exit(1)

    finally:
        qmp.sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="Forward input events into QEMU Win98 guest via QMP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --qmp /tmp/qemu.sock --scroll-only     # Scroll wheel only
  %(prog)s --qmp /tmp/qemu.sock                    # Mirror host input
  %(prog)s --qmp /tmp/qemu.sock --capture           # Exclusive capture
  %(prog)s --qmp /tmp/qemu.sock --remote            # Network input server
  %(prog)s --qmp /tmp/qemu.sock --inject --type "Hello"
  %(prog)s --qmp /tmp/qemu.sock --inject --click 16000 8000
  %(prog)s --qmp /tmp/qemu.sock --inject --key combo ctrl alt delete
        """,
    )

    # ── Global options ──────────────────────────────────────
    parser.add_argument(
        "--qmp", required=True,
        help="Path to QEMU QMP Unix socket",
    )
    parser.add_argument(
        "--capture", action="store_true",
        help="Capture mode: suppress events from host (exclusive)",
    )
    parser.add_argument(
        "--scroll-only", action="store_true",
        help="Only forward scroll wheel events (mouse/keyboard handled by QEMU usb-tablet)",
    )
    parser.add_argument(
        "--scroll-keys", choices=["arrows", "space"], default="arrows",
        help="Scroll key mapping: arrows (Arrow Up/Down, default) or space (Space/Shift+Space for browsers)",
    )
    parser.add_argument(
        "--app", action="store_true",
        help="Launch as macOS menu bar app with floating overlay",
    )
    parser.add_argument(
        "--remote", action="store_true",
        help="Remote mode: listen for TCP input events",
    )
    parser.add_argument(
        "--inject", action="store_true",
        help="Inject mode: one-shot input injection",
    )

    # ── Remote mode options ─────────────────────────────────
    parser.add_argument("--listen", default="0.0.0.0", help="Remote listen host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9999, help="Remote listen port (default: 9999)")

    # ── Inject mode options ─────────────────────────────────
    parser.add_argument("--type", dest="type_text", help="Type a string into the guest")
    parser.add_argument("--click", type=int, nargs=2, metavar=("X", "Y"), help="Click at absolute position")
    parser.add_argument("--key", nargs="+", metavar="KEY", help="Send key(s). Use 'combo' first for combo")
    parser.add_argument("--move", type=int, nargs=2, metavar=("X", "Y"), help="Move mouse to absolute position")
    parser.add_argument("--delay", type=int, default=30, help="Delay between events in ms (default: 30)")

    args = parser.parse_args()

    try:
        if args.inject:
            cmd_inject(args)
        elif args.remote:
            cmd_remote(args)
        else:
            cmd_local(args)
    except QMPError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Make sure QEMU is running with: -qmp unix:%s,server,nowait" % args.qmp)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: QMP socket not found: {args.qmp}", file=sys.stderr)
        print("Make sure QEMU is running and the socket path is correct.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
