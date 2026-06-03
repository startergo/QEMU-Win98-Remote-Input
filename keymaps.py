"""
Keycode mapping tables for translating platform-specific keycodes
to QEMU qcode strings used by the QMP input-send-event command.
"""

# ── macOS virtual keycode → QEMU qcode ────────────────────────
# Based on Apple's <Events.h> kVK_* constants
# Full reference: https://developer.apple.com/library/archive/technotes/tn2450/

MAC_VK_TO_QCODE = {
    # Letters
    0x00: "a",  0x0B: "b",  0x08: "c",  0x02: "d",  0x0E: "e",
    0x03: "f",  0x05: "g",  0x04: "h",  0x22: "i",  0x26: "j",
    0x28: "k",  0x25: "l",  0x2E: "m",  0x2D: "n",  0x1F: "o",
    0x23: "p",  0x0C: "q",  0x0F: "r",  0x01: "s",  0x11: "t",
    0x20: "u",  0x09: "v",  0x0D: "w",  0x07: "x",  0x10: "y",
    0x06: "z",

    # Numbers (top row)
    0x12: "1",  0x13: "2",  0x14: "3",  0x15: "4",  0x17: "5",
    0x16: "6",  0x1A: "7",  0x1C: "8",  0x19: "9",  0x1D: "0",

    # Punctuation
    0x27: "apostrophe",  0x29: "semicolon",  0x2A: "backslash",
    0x2B: "comma",       0x2F: "dot",        0x2C: "slash",
    0x18: "equal",       0x1B: "minus",
    0x21: "bracket_left",  0x1E: "bracket_right",
    0x32: "grave_accent",

    # Whitespace / editing
    0x31: "spc",       0x24: "ret",          0x30: "tab",
    0x33: "backspace",  0x35: "esc",

    # Modifiers
    0x38: "shift",       0x3C: "shift_r",      # Left / Right Shift
    0x3B: "ctrl",        0x36: "ctrl_r",        # Left / Right Control
    0x3A: "alt",         0x3D: "alt_r",         # Left / Right Option
    0x37: "meta_l",      0x3E: "meta_r",        # Left / Right Command
    0x39: "caps_lock",

    # Function keys
    0x7A: "f1",   0x78: "f2",   0x63: "f3",   0x76: "f4",
    0x60: "f5",   0x61: "f6",   0x62: "f7",   0x64: "f8",
    0x65: "f9",   0x6D: "f10",  0x67: "f11",  0x6F: "f12",
    0x69: "f13",  0x6B: "f14",  0x71: "f15",

    # Navigation
    0x73: "home",   0x77: "end",   0x74: "pgup",  0x79: "pgdn",
    0x72: "help",   0x75: "delete",

    # Arrow keys
    0x7B: "left",   0x7C: "right",  0x7D: "down",  0x7E: "up",

    # Keypad
    0x52: "kp_0",  0x53: "kp_1",  0x54: "kp_2",  0x55: "kp_3",
    0x56: "kp_4",  0x57: "kp_5",  0x58: "kp_6",  0x59: "kp_7",
    0x5B: "kp_8",  0x5C: "kp_9",
    0x41: "kp_decimal",  0x43: "kp_multiply",  0x45: "kp_add",
    0x4E: "kp_subtract",  0x4B: "kp_divide",   0x4C: "kp_enter",
    0x47: "num_lock",

    # Misc
    0x40: "f17",  0x48: "volup",  0x49: "voldown",  0x4A: "mute",
}

# Reverse mapping: QEMU qcode → macOS virtual keycode
QCODE_TO_MAC_VK = {v: k for k, v in MAC_VK_TO_QCODE.items()}


# ── Linux evdev keycode → QEMU qcode ──────────────────────────
# Based on <linux/input-event-codes.h> KEY_* constants

EVDEV_KEY_TO_QCODE = {
    # Letters
    0x1E: "a",  0x30: "b",  0x2E: "c",  0x20: "d",  0x12: "e",
    0x21: "f",  0x22: "g",  0x23: "h",  0x17: "i",  0x24: "j",
    0x25: "k",  0x26: "l",  0x32: "m",  0x31: "n",  0x18: "o",
    0x19: "p",  0x10: "q",  0x13: "r",  0x1F: "s",  0x14: "t",
    0x16: "u",  0x2F: "v",  0x11: "w",  0x2D: "x",  0x15: "y",
    0x2C: "z",

    # Numbers (top row)
    0x02: "1",  0x03: "2",  0x04: "3",  0x05: "4",  0x06: "5",
    0x07: "6",  0x08: "7",  0x09: "8",  0x0A: "9",  0x0B: "0",

    # Punctuation
    0x28: "apostrophe",  0x27: "semicolon",  0x2B: "backslash",
    0x33: "comma",       0x34: "dot",        0x35: "slash",
    0x0D: "equal",       0x0C: "minus",
    0x1A: "bracket_left",  0x1B: "bracket_right",
    0x29: "grave_accent",

    # Whitespace / editing
    0x39: "spc",       0x1C: "ret",          0x0F: "tab",
    0x0E: "backspace",  0x01: "esc",

    # Modifiers
    0x2A: "shift",       0x36: "shift_r",
    0x1D: "ctrl",        0x61: "ctrl_r",
    0x38: "alt",         0x64: "alt_r",
    0x7D: "meta_l",      0x7E: "meta_r",
    0x3A: "caps_lock",

    # Function keys
    0x3B: "f1",   0x3C: "f2",   0x3D: "f3",   0x3E: "f4",
    0x3F: "f5",   0x40: "f6",   0x41: "f7",   0x42: "f8",
    0x43: "f9",   0x44: "f10",  0x57: "f11",  0x58: "f12",
    0x59: "f13",  0x5A: "f14",  0x5B: "f15",

    # Navigation
    0x47: "home",   0x4F: "end",   0x49: "pgup",  0x51: "pgdn",
    0x53: "num_lock", 0xD2: "insert", 0xD3: "delete",

    # Arrow keys
    0x4B: "left",   0x4D: "right",  0x50: "down",  0x48: "up",

    # Keypad (only entries with unique evdev codes; shared codes are
    # mapped to their navigation/arrow equivalents above — the kernel
    # produces the correct evdev code based on NumLock state)
    0x37: "kp_multiply", 0x4E: "kp_add",
    0x4A: "kp_subtract", 0x60: "kp_enter",
    0x52: "kp_0",  0x4C: "kp_5",

    # Multimedia
    0x6C: "volup",  0x6E: "voldown",  0x71: "mute",

    # Print Screen / Pause
    0x54: "sysrq",  0x55: "sysrq",   0x56: "less",
    0x62: "sysrq",  0x63: "wake",
    0x65: "suspend", 0x66: "henkan",
    0x67: "muhenkan", 0x68: "kp_comma",
    0x7F: "audioplay",
}

# Reverse mapping: QEMU qcode → evdev keycode
QCODE_TO_EVDEV_KEY = {v: k for k, v in EVDEV_KEY_TO_QCODE.items()}


# ── Complete list of valid QEMU qcodes ────────────────────────
# Used for validation and reference

VALID_QCODES = sorted(set(
    list(MAC_VK_TO_QCODE.values()) +
    list(EVDEV_KEY_TO_QCODE.values())
))
