# QEMU Win98 Remote Input

Forward macOS/Linux input events into a QEMU Windows 98 guest via QMP.

A macOS-native equivalent of [remote-evdev-python](https://github.com/Surferlul/remote-evdev-python) that works with **any** QEMU guest OS — Windows 98, DOS, OS/2, etc. No guest-side drivers needed for mouse and keyboard.

## How It Works

```
┌─────────────────────┐     QMP      ┌──────────────┐     USB HID    ┌──────────────┐
│  macOS CGEvent      │────socket───▶│  QEMU        │──emulation────▶│  Win98 Guest │
│  or Linux evdev     │   (JSON)     │  input layer │   (ps2/usb)    │  sees real   │
│  or remote TCP      │              │              │                │  input device│
└─────────────────────┘              └──────────────┘                └──────────────┘
```

## Features

- 🖥️ **macOS native** — captures input via CGEvent tap (no evdev needed)
- 🖱️ **Scroll** — two-finger trackpad swipe forwarded as keystrokes (Arrow keys or Space/Shift+Space, switchable with `--scroll-keys`)
- 🎯 **Absolute mouse** — maps screen coordinates to HID range (0–32767) via usb-tablet
- ⌨️ **Full keyboard** — maps macOS/Linux keycodes to QEMU qcodes
- 🔄 **Mirror or capture mode** — non-intrusive or exclusive input forwarding
- 🌐 **Remote mode** — accept input events over TCP from any machine
- 💉 **Inject mode** — one-shot automation (type strings, click coordinates, send key combos)
- 🐧 **Linux remote sender** — forward evdev devices from a Linux machine over TCP

## Requirements

- QEMU with QMP support + `-device usb-tablet`
- Python 3.10+
- macOS: `pip3 install -r requirements.txt --break-system-packages`
- Linux (optional): `pip3 install evdev`

## Quick Start

### 1. Add QMP to your QEMU config

```bash
-qmp unix:/tmp/qemu-win98.sock,server,nowait
```

<details>
<summary>Full QEMU command example</summary>

```bash
qemu-system-i386 -nodefaults -rtc base=localtime -display sdl -monitor stdio \
    -name "Windows 98" \
    -M pc,accel=tcg,usb=off -cpu max -m 512 \
    -device VGA \
    -device lsi \
    -audiodev coreaudio,id=snd0,out.frequency=44100,out.channels=2,out.format=s16 \
    -device ac97,audiodev=snd0 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 -device pcnet,rombar=0,netdev=net0 \
    -drive id=fd01,if=floppy,format=raw,file=fd.ima \
    -drive id=win98,if=none,file=win98.qcow2 -device scsi-hd,drive=win98 \
    -drive id=icd04,if=none,media=cdrom,file=vmaddons.iso -device ide-cd,drive=icd04 \
    -usb \
    -device usb-tablet \
    -serial pty \
    -qmp unix:/tmp/qemu-win98.sock,server,nowait \
    -boot menu=on
```

</details>

### 2. Run

**Menu bar app** (recommended — native macOS app with floating overlay, switch modes from menu bar):

```bash
python3 main.py --qmp /tmp/qemu-win98.sock --scroll-only --app
```

**Scroll-only mode** (terminal — only forwards scroll, mouse/keyboard handled by QEMU's usb-tablet natively):

```bash
# Arrow keys — line-by-line scroll (Explorer, text editors, general use)
python3 main.py --qmp /tmp/qemu-win98.sock --scroll-only

# Space/Shift+Space — page scroll (web browsers, Browservice)
python3 main.py --qmp /tmp/qemu-win98.sock --scroll-only --scroll-keys space
```

<details>
<summary>Other modes</summary>

**Mirror mode** (events go to both host and guest):
```bash
python3 main.py --qmp /tmp/qemu-win98.sock
```

**Capture mode** (exclusive — only guest gets input):
```bash
python3 main.py --qmp /tmp/qemu-win98.sock --capture
```

</details>

> **Accessibility Permission Required:** On first run, macOS will prompt you to grant Accessibility access to your Terminal or Python. Go to **System Settings → Privacy & Security → Accessibility** and enable it.

---

<details>
<summary>📖 Modes — detailed usage</summary>

### Local (macOS CGEvent capture)

Captures keyboard and mouse events directly from macOS using a CGEvent tap.

```bash
# Mirror — both host and guest receive events
python3 main.py --qmp /tmp/qemu-win98.sock

# Capture — only guest receives events (host is suppressed)
python3 main.py --qmp /tmp/qemu-win98.sock --capture
```

### Remote (TCP input server)

Listens for JSON input events over TCP. Useful for forwarding input from another machine.

```bash
# On macOS QEMU host:
python3 main.py --qmp /tmp/qemu-win98.sock --remote --port 9999

# From a Linux machine:
python3 remote_sender.py --host 192.168.1.100 --port 9999 \
    --keyboard /dev/input/event0 --mouse /dev/input/event1

# Or auto-detect all keyboards and mice:
python3 remote_sender.py --host 192.168.1.100 --auto
```

**Network protocol** — newline-delimited JSON:

```json
{"type": "key",     "key": "a",       "down": true}
{"type": "abs",     "x": 16384,       "y": 8192}
{"type": "rel",     "dx": 10,         "dy": -5}
{"type": "btn",     "button": "left",  "down": true}
{"type": "scroll",  "dy": 3,          "dx": 0}              → mapped to Arrow/Space keys
```

### Inject (one-shot automation)

For scripting, testing, or automation tasks.

```bash
# Type a string
python3 main.py --qmp /tmp/qemu-win98.sock --inject --type "Hello Win98!"

# Click at position (HID coordinates 0-32767)
python3 main.py --qmp /tmp/qemu-win98.sock --inject --click 16384 8192

# Send a key combo (Ctrl+Alt+Delete)
python3 main.py --qmp /tmp/qemu-win98.sock --inject --key combo ctrl alt delete

# Send individual keys
python3 main.py --qmp /tmp/qemu-win98.sock --inject --key ret tab escape

# Move mouse to position
python3 main.py --qmp /tmp/qemu-win98.sock --inject --move 20000 10000

# Custom delay between keystrokes (ms)
python3 main.py --qmp /tmp/qemu-win98.sock --inject --type "slow" --delay 100
```

</details>

<details>
<summary>🔧 Technical Details</summary>

### Mouse Coordinate Mapping

The `usb-tablet` device uses HID absolute coordinates (0–32767). The tool maps your screen resolution to this range:

```
  macOS screen (e.g. 2560x1600)           QEMU usb-tablet HID
  ┌────────────────────────┐              ┌──────────────────────┐
  │ 0,0            2560,0  │              │ 0,0          32767,0 │
  │                        │              │                      │
  │           1280, 800    │   ────▶      │        16384, 16384  │
  │                        │              │                      │
  │ 0,1600      2560,1600  │              │ 0,32767  32767,32767 │
  └────────────────────────┘              └──────────────────────┘
```

### Why Not remote-evdev-python or HIDInjector?

| | remote-evdev-python | HIDInjector | This tool |
|---|---|---|---|
| Runs inside guest | ❌ (needs Linux) | ✅ (needs Win10+) | ❌ (runs on host) |
| Transport | TCP → uinput | WriteFile → VHF kernel driver | QMP → QEMU input layer |
| Guest requirements | Linux evdev + uinput | Windows 10 VHF | **None** |
| Win98 compatible | ❌ | ❌ | ✅ |
| macOS host | ❌ (evdev only) | N/A | ✅ (CGEvent) |
| Linux remote | ✅ | N/A | ✅ (evdev) |
| Absolute mouse | ✅ (uinput) | ✅ (HID descriptor) | ✅ (usb-tablet) |
| Scroll | ❌ | ✅ | ✅ (Arrow/Space keys via QMP) |

### File Structure

```
qemu-win98-remote-input/
├── main.py              # CLI entry point (macOS host)
├── app.py               # macOS menu bar app + floating overlay
├── qmp_client.py        # QMP protocol client
├── keymaps.py           # macOS/Linux → QEMU keycode mappings
├── macos_input.py       # macOS CGEvent input capture
├── network.py           # TCP network protocol (send/receive)
├── remote_sender.py     # Linux evdev remote sender
├── launch-win98.sh      # Example QEMU launch script
├── requirements.txt     # Python dependencies
├── LICENSE              # MIT License
└── README.md            # This file
```

</details>

<details>
<summary>❓ Troubleshooting</summary>

### "Cannot create CGEvent tap"
Grant Accessibility permissions:
1. System Settings → Privacy & Security → Accessibility
2. Add your Terminal app or Python interpreter
3. On macOS Sonoma+, you may need to remove and re-add after updates

### "QMP socket not found"
- Ensure QEMU is running with `-qmp unix:/tmp/qemu-win98.sock,server,nowait`
- Check the socket path matches

### Mouse is offset or not aligned
- The tool normalizes to your main display. If using multiple displays, the mapping may be off.
- Use `--capture` mode for best results — the mouse will be locked to the VM.

### Keys not mapping correctly
- See `keymaps.py` for the full keycode tables
- File an issue with the specific key and macOS keyboard layout

### Connection refused (remote mode)
- Ensure the remote server is running on the QEMU host:
  ```bash
  python3 main.py --qmp /tmp/qemu-win98.sock --remote
  ```
- Check firewall settings on both machines

### Scroll not working in Win98
- Two-finger swipe is mapped to keyboard keys (not a real scroll wheel)
- **`--scroll-keys arrows`** (default) — Arrow Up/Down. Works in Explorer, text editors, most apps
- **`--scroll-keys space`** — Space/Shift+Space. Works in web browsers (Browservice)
- Switch modes at any time by restarting with a different `--scroll-keys` value

### Using with launch-win98.sh

The included launch script starts QEMU with QMP and optionally starts the remote server:

```bash
chmod +x launch-win98.sh

# Start QEMU with QMP
./launch-win98.sh

# Start QEMU + remote input server
./launch-win98.sh --remote

# Headless mode
./launch-win98.sh --headless --remote
```

</details>

## License

MIT
