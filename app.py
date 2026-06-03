"""
macOS menu bar app + floating overlay for QEMU Win98 scroll forwarding.

Provides a native menu bar icon with:
  - Toggle scroll mode (Arrows / Space)
  - Start / Stop forwarding
  - Connection status
  - Floating overlay showing current mode

Uses PyObjC to integrate with the existing CFRunLoop-based CGEvent tap.
"""

import sys
import objc
from Foundation import NSObject, NSRunLoop
from AppKit import (
    NSApplication, NSApp, NSMenu, NSMenuItem, NSImage, NSColor, NSFont,
    NSWindow, NSView, NSTextField, NSMakeRect,
    NSBorderlessWindowMask, NSFloatingWindowLevel,
    NSStatusWindowLevel, NSBackgroundColorAttributeName,
    NSFontAttributeName, NSForegroundColorAttributeName,
    NSAttributedString, NSStatusBar, NSVariableStatusItemLength,
    NSApplicationActivationPolicyAccessory, NSBezierPath,
)


class ScrollOverlay(NSObject):
    """Small floating overlay showing current scroll mode."""

    def init(self):
        self = objc.super(ScrollOverlay, self).init()
        if self is None:
            return None
        self._window = None
        self._label = None
        self._mode = "arrows"
        return self

    def createOverlay(self):
        """Create the floating overlay window."""
        width, height = 140, 32
        # Position: bottom-right of screen, above dock
        from Quartz import CGDisplayBounds, CGMainDisplayID
        rect = CGDisplayBounds(CGMainDisplayID())
        screen_w = int(rect.size.width)
        screen_h = int(rect.size.height)
        x = screen_w - width - 20
        y = 80  # above dock area

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            NSBorderlessWindowMask,
            2,  # NSBackingStoreBuffered
            False,
        )
        self._window.setLevel_(NSStatusWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setAlphaValue_(0.85)
        self._window.setMovableByWindowBackground_(False)
        self._window.setIgnoresMouseEvents_(True)
        from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)

        # Background view with rounded corners
        bg = OverlayView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        self._window.setContentView_(bg)

        # Label
        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(8, 4, width - 16, height - 8))
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setBezeled_(False)
        self._label.setDrawsBackground_(False)
        self._label.setAlignment_(2)  # NSCenterTextAlignment
        self.updateLabel()
        bg.addSubview_(self._label)

        self._window.orderFront_(None)
        return self

    def setMode_(self, mode):
        self._mode = mode
        self.updateLabel()

    def updateLabel(self):
        if self._label is None:
            return
        icon = "⬆⬇" if self._mode == "arrows" else "␣⇧"
        text = f"{icon}  {self._mode.upper()}"
        font = NSFont.systemFontOfSize_weight_(13, 6)  # medium weight
        attrs = {
            NSFontAttributeName: font,
            NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        attr_str = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        self._label.setAttributedStringValue_(attr_str)

    def show(self):
        if self._window:
            self._window.orderFront_(None)

    def hide(self):
        if self._window:
            self._window.orderOut_(None)


class OverlayView(NSView):
    """Custom view with rounded rect background for the overlay."""

    def drawRect_(self, rect):
        radius = 10
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), radius, radius
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.15, 0.15, 0.15, 0.9).set()
        path.fill()


def create_status_image():
    """Create a simple scroll icon for the menu bar."""
    # Use a system symbol if available (macOS 11+), else text
    try:
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "scroll", "Scroll"
        )
        if image:
            return image
    except Exception:
        pass
    # Fallback: create a text-based icon
    return None


class MenuBarController(NSObject):
    """Manages the menu bar status item, menu, and overlay."""

    def initWithQMP_scrollKeys_(self, qmp, scroll_keys):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return None
        self._qmp = qmp
        self._scroll_keys = scroll_keys  # "arrows" or "space"
        self._active = True
        self._overlay = None
        return self

    def setup(self):
        """Create the menu bar item, menu, and overlay."""
        # ── Status bar item ──
        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)

        image = create_status_image()
        if image:
            self._status_item.button().setImage_(image)
        self._status_item.button().setTitle_("Scroll")
        self._status_item.button().setToolTip_("QEMU Win98 Scroll Forwarder")

        # ── Menu ──
        menu = NSMenu.alloc().init()

        # Scroll mode submenu
        mode_menu = NSMenu.alloc().init()
        arrows_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Arrow Keys (line-by-line)", "switchToArrows:", ""
        )
        arrows_item.setTarget_(self)
        space_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Space / Shift+Space (browsers)", "switchToSpace:", ""
        )
        space_item.setTarget_(self)
        if self._scroll_keys == "arrows":
            arrows_item.setState_(1)  # NSOnState
        else:
            space_item.setState_(1)
        mode_menu.addItem_(arrows_item)
        mode_menu.addItem_(space_item)

        mode_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Scroll Mode", None, ""
        )
        mode_item.setSubmenu_(mode_menu)
        menu.addItem_(mode_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # Toggle
        self._toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause Scroll Forwarding", "toggleActive:", ""
        )
        self._toggle_item.setTarget_(self)
        menu.addItem_(self._toggle_item)

        # Toggle overlay visibility
        self._overlay_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Hide Overlay", "toggleOverlay:", ""
        )
        self._overlay_item.setTarget_(self)
        menu.addItem_(self._overlay_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q"
        )
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)

        # ── Floating overlay ──
        self._overlay = ScrollOverlay.alloc().init()
        self._overlay.createOverlay()
        self._overlay.setMode_(self._scroll_keys)

    # ── Menu actions ──

    def switchToArrows_(self, sender):
        self._scroll_keys = "arrows"
        self._update_menu_checks()
        self._overlay.setMode_("arrows")

    def switchToSpace_(self, sender):
        self._scroll_keys = "space"
        self._update_menu_checks()
        self._overlay.setMode_("space")

    def toggleActive_(self, sender):
        self._active = not self._active
        if self._active:
            self._toggle_item.setTitle_("Pause Scroll Forwarding")
            self._status_item.button().setTitle_("Scroll")
        else:
            self._toggle_item.setTitle_("Resume Scroll Forwarding")
            self._status_item.button().setTitle_("Scroll (paused)")

    def toggleOverlay_(self, sender):
        if self._overlay._window.isVisible():
            self._overlay.hide()
            sender.setTitle_("Show Overlay")
        else:
            self._overlay.show()
            sender.setTitle_("Hide Overlay")

    def _update_menu_checks(self):
        menu = self._status_item.menu()
        mode_item = menu.itemAtIndex_(0)
        submenu = mode_item.submenu()
        arrows = submenu.itemAtIndex_(0)
        space = submenu.itemAtIndex_(1)
        arrows.setState_(1 if self._scroll_keys == "arrows" else 0)
        space.setState_(1 if self._scroll_keys == "space" else 0)

    @property
    def scroll_keys(self):
        return self._scroll_keys

    @property
    def active(self):
        return self._active


def run_app(qmp, scroll_keys="arrows"):
    """Launch the menu bar app with scroll forwarding.

    Args:
        qmp: Connected QMPClient instance.
        scroll_keys: Initial scroll mode ("arrows" or "space").
    """
    # Set up NSApplication (accessory = no dock icon)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    # Create menu bar controller
    controller = MenuBarController.alloc().initWithQMP_scrollKeys_(qmp, scroll_keys)
    controller.setup()

    # Import scroll capture
    from macos_input import start_capture

    # Start CGEvent capture with callback that checks controller state
    _start_scroll_capture(qmp, controller)

    # Run the app (use Quit from menu bar to exit — Ctrl+C doesn't work with NSApp)
    NSApp.run()


def _start_scroll_capture(qmp, controller):
    """Start CGEvent tap for scroll events, reading mode from controller."""
    try:
        from Quartz import (
            CGEventTapCreate, kCGSessionEventTap, kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly, kCGEventScrollWheel,
            CGEventTapEnable,
            CFMachPortCreateRunLoopSource, CFRunLoopGetCurrent,
            CFRunLoopAddSource, kCFRunLoopCommonModes,
            CGEventGetIntegerValueField,
            kCGScrollWheelEventDeltaAxis1, kCGScrollWheelEventDeltaAxis2,
        )
    except ImportError:
        print("ERROR: pyobjc-framework-Quartz not installed.")
        print("  Run: pip3 install pyobjc-framework-Quartz")
        sys.exit(1)

    stats = {"scrolls": 0}

    event_mask = 1 << kCGEventScrollWheel

    def callback(proxy, event_type, event, refcon):
        try:
            if event_type == kCGEventScrollWheel and controller.active:
                dy = CGEventGetIntegerValueField(event, kCGScrollWheelEventDeltaAxis1)
                dy = max(-10, min(10, dy))
                if dy:
                    qmp.send_scroll(dy, keys=controller.scroll_keys)
                    stats["scrolls"] += 1
            return event
        except Exception as e:
            print(f"[!] Event error: {e}", file=sys.stderr)
            return event

    tap = CGEventTapCreate(
        kCGSessionEventTap, kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly, event_mask, callback, None,
    )

    if not tap:
        print("ERROR: Cannot create CGEvent tap.")
        print("Grant Accessibility permissions:")
        print("  System Settings → Privacy & Security → Accessibility")
        sys.exit(1)

    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)

    mode_label = "Arrow Keys ⬆⬇" if controller.scroll_keys == "arrows" else "Space/Shift+Space ␣⇧"
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  macOS Scroll → QEMU Win98 via QMP           ║")
    print(f"║  Mode: {mode_label:<37s}                     ║")
    print(f"║  Click 'Scroll' in menu bar to change mode   ║")
    print(f"║  Quit from menu bar to stop (Ctrl+C won't)   ║")
    print(f"╚══════════════════════════════════════════════╝")
