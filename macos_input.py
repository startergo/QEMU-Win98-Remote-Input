"""
macOS input capture using CGEvent tap.

Captures keyboard and mouse events from macOS and forwards them to a
QEMU guest via QMP. Supports both mirror mode (events go to both host
and guest) and capture mode (events are intercepted exclusively for guest).

Requires Accessibility permissions:
  System Settings → Privacy & Security → Accessibility → Add Terminal/Python
"""

import sys
import signal

from qmp_client import QMPClient
from keymaps import MAC_VK_TO_QCODE


def _get_screen_size():
    """Get main display dimensions."""
    from Quartz import CGDisplayBounds, CGMainDisplayID
    rect = CGDisplayBounds(CGMainDisplayID())
    return rect.size.width, rect.size.height


def start_capture(qmp, capture=False, screen_size=None, scroll_only=False, scroll_keys="arrows"):
    """
    Start capturing macOS input events and forwarding to QEMU.

    Args:
        qmp: Connected QMPClient instance.
        capture: If True, suppress events from host (exclusive mode).
                 If False, mirror events to both host and guest.
        screen_size: Optional (width, height) tuple. Auto-detected if None.
        scroll_only: If True, only forward scroll wheel events. Mouse and
                     keyboard are left to QEMU's native usb-tablet handling.
    """
    try:
        from Quartz import (
            CGEventTapCreate, kCGSessionEventTap, kCGHeadInsertEventTap,
            kCGEventTapOptionDefault, kCGEventTapOptionListenOnly,
            kCGEventKeyDown, kCGEventKeyUp, kCGEventFlagsChanged,
            kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
            kCGEventRightMouseDown, kCGEventRightMouseUp,
            kCGEventOtherMouseDown, kCGEventOtherMouseUp,
            kCGEventLeftMouseDragged, kCGEventRightMouseDragged,
            kCGEventOtherMouseDragged, kCGEventScrollWheel,
            kCGKeyboardEventKeycode,
            CFMachPortCreateRunLoopSource, CFRunLoopGetCurrent,
            CFRunLoopAddSource, kCFRunLoopCommonModes,
            CGEventTapEnable,
            CGEventGetIntegerValueField, CGEventGetLocation,
            kCGScrollWheelEventDeltaAxis1, kCGScrollWheelEventDeltaAxis2,
            CFRunLoopRun,
        )
    except ImportError:
        print("ERROR: pyobjc-framework-Quartz not installed.")
        print("  Run: pip install pyobjc-framework-Quartz")
        sys.exit(1)

    if screen_size:
        screen_w, screen_h = screen_size
    else:
        screen_w, screen_h = _get_screen_size()

    # HID coordinate range for usb-tablet (0-32767)
    HID_MAX = 32767

    # ── Statistics ──────────────────────────────────────────
    stats = {"keys": 0, "moves": 0, "clicks": 0, "scrolls": 0}

    # ── Build event mask ────────────────────────────────────
    event_mask = (
        (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp) |
        (1 << kCGEventFlagsChanged) |
        (1 << kCGEventMouseMoved) | (1 << kCGEventLeftMouseDragged) |
        (1 << kCGEventLeftMouseDown) | (1 << kCGEventLeftMouseUp) |
        (1 << kCGEventRightMouseDown) | (1 << kCGEventRightMouseUp) |
        (1 << kCGEventOtherMouseDown) | (1 << kCGEventOtherMouseUp) |
        (1 << kCGEventScrollWheel)
    )

    tap_option = (
        kCGEventTapOptionDefault if capture
        else kCGEventTapOptionListenOnly
    )

    # ── Event callback ──────────────────────────────────────
    def callback(proxy, event_type, event, refcon):
        try:
            # ─ Scroll wheel (two-finger trackpad or mouse wheel) ──
            if event_type == kCGEventScrollWheel:
                # Axis 1 = vertical, Axis 2 = horizontal
                # macOS reports "pixels" for trackpad, "lines" for mouse wheel.
                # Clamp to avoid flooding QEMU with huge deltas.
                dy = CGEventGetIntegerValueField(event, kCGScrollWheelEventDeltaAxis1)
                dx = CGEventGetIntegerValueField(event, kCGScrollWheelEventDeltaAxis2)
                # Normalize trackpad momentum (large pixel deltas) to line-like units
                dy = max(-10, min(10, dy))
                dx = max(-10, min(10, dx))
                if dy or dx:
                    qmp.send_scroll(dy, dx, keys=scroll_keys)
                    stats["scrolls"] += 1
                return None if capture else event

            # In scroll-only mode, skip mouse and keyboard forwarding
            # (handled natively by QEMU's usb-tablet / SDL display)
            if scroll_only:
                return event

            # ─ Keyboard ───────────────────────────────────
            if event_type in (kCGEventKeyDown, kCGEventKeyUp):
                keycode = CGEventGetIntegerValueField(
                    event, kCGKeyboardEventKeycode
                )
                qcode = MAC_VK_TO_QCODE.get(keycode)
                if qcode:
                    down = (event_type == kCGEventKeyDown)
                    qmp.send_key(qcode, down)
                    stats["keys"] += 1
                return None if capture else event

            # ─ Mouse move / drag ──────────────────────────
            if event_type in (kCGEventMouseMoved,
                              kCGEventLeftMouseDragged,
                              kCGEventRightMouseDragged,
                              kCGEventOtherMouseDragged):
                loc = CGEventGetLocation(event)
                norm_x = int((loc.x / screen_w) * HID_MAX)
                norm_y = int((loc.y / screen_h) * HID_MAX)
                # Clamp to valid range
                norm_x = max(0, min(HID_MAX, norm_x))
                norm_y = max(0, min(HID_MAX, norm_y))
                qmp.send_mouse_abs(norm_x, norm_y)
                stats["moves"] += 1
                return None if capture else event

            # ─ Mouse buttons ──────────────────────────────
            button_map = {
                kCGEventLeftMouseDown:   ("left",   True),
                kCGEventLeftMouseUp:     ("left",   False),
                kCGEventRightMouseDown:  ("right",  True),
                kCGEventRightMouseUp:    ("right",  False),
                kCGEventOtherMouseDown:  ("middle", True),
                kCGEventOtherMouseUp:    ("middle", False),
            }
            if event_type in button_map:
                button, down = button_map[event_type]
                qmp.send_mouse_btn(button, down)
                stats["clicks"] += 1
                return None if capture else event

        except Exception as e:
            print(f"[!] Event error: {e}", file=sys.stderr)

        return event

    # ── Create and enable tap ────────────────────────────────
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        tap_option,
        event_mask,
        callback,
        None,
    )

    if not tap:
        print("ERROR: Cannot create CGEvent tap.")
        print()
        print("Grant Accessibility permissions:")
        print("  System Settings → Privacy & Security → Accessibility")
        print("  → Add your Terminal app or Python interpreter")
        print()
        print("On macOS Sonoma+, you may need to:")
        print("  1. Remove and re-add the app after each update")
        print("  2. Use 'tccutil reset Accessibility' to reset")
        sys.exit(1)

    # ── Run loop ─────────────────────────────────────────────
    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)

    if scroll_only:
        mode = "SCROLL ONLY"
    elif capture:
        mode = "CAPTURE (exclusive)"
    else:
        mode = "MIRROR (non-intrusive)"
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  macOS Input → QEMU Win98 via QMP           ║")
    print(f"║  Mode: {mode:<37s}║")
    if not scroll_only:
        print(f"║  Screen: {screen_w:.0f}×{screen_h:.0f} → HID 0-{HID_MAX:<15d}║")
    print(f"║  Press Ctrl+C to stop                       ║")
    print(f"╚══════════════════════════════════════════════╝")

    try:
        CFRunLoopRun()
    except KeyboardInterrupt:
        CGEventTapEnable(tap, False)
        print(f"\nStats: {stats['keys']} keys, {stats['moves']} moves, {stats['clicks']} clicks, {stats['scrolls']} scrolls")
        print("Stopped.")
