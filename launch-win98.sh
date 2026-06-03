#!/bin/sh
# ──────────────────────────────────────────────────────────────
# launch-win98.sh — Example QEMU Windows 98 launch script
#
# This script starts QEMU with QMP support enabled so that the
# remote input tool can connect and forward input events.
#
# Usage:
#   ./launch-win98.sh                    # Start VM with QMP
#   ./launch-win98.sh --remote           # Also start remote input server
#   ./launch-win98.sh --with-clipboard    # Start with serial clipboard helper
# ──────────────────────────────────────────────────────────────

set -e

# ── Configuration ────────────────────────────────────────────
VM_NAME="Windows 98"
QMP_SOCK="/tmp/qemu-win98.sock"
DISK_IMAGE="win98.qcow2"
FLOPPY_IMAGE="fd.ima"
CDROM_IMAGE="vmaddons.iso"
RAM_MB=512
REMOTE_PORT=9999

# ── Cleanup old QMP socket ───────────────────────────────────
rm -f "$QMP_SOCK"

# ── Parse arguments ──────────────────────────────────────────
START_REMOTE=0
START_CLIPBOARD=0
CLIP98_BIN="clip98-darwin-arm64"
EXTRA_ARGS=""

for arg in "$@"; do
    case "$arg" in
        --remote)
            START_REMOTE=1
            ;;
        --with-clipboard)
            START_CLIPBOARD=1
            ;;
        --vnc)
            EXTRA_ARGS="$EXTRA_ARGS -display vnc=:0"
            ;;
        --headless)
            EXTRA_ARGS="$EXTRA_ARGS -display none"
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--remote] [--with-clipboard] [--vnc] [--headless]"
            exit 1
            ;;
    esac
done

# ── Start QEMU ───────────────────────────────────────────────
echo "Starting QEMU: $VM_NAME"
echo "QMP socket: $QMP_SOCK"

# Only include floppy drive if image exists
if [ -f "$FLOPPY_IMAGE" ]; then
    FLOPPY_DRIVE=1
fi

qemu-system-i386 \
    -nodefaults \
    -rtc base=localtime \
    -display sdl \
    -monitor stdio \
    -name "$VM_NAME" \
    -M pc,accel=tcg,usb=off \
    -cpu max \
    -m $RAM_MB \
    -device VGA \
    -device lsi \
    -audiodev coreaudio,id=snd0,out.frequency=44100,out.channels=2,out.format=s16 \
    -device ac97,audiodev=snd0 \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device pcnet,rombar=0,netdev=net0 \
    ${FLOPPY_DRIVE:+-drive id=fd01,if=floppy,format=raw,file="$FLOPPY_IMAGE"} \
    -drive id=win98,if=none,file="$DISK_IMAGE" \
    -device scsi-hd,drive=win98 \
    -drive id=icd04,if=none,media=cdrom,file="$CDROM_IMAGE" \
    -device ide-cd,drive=icd04 \
    -usb \
    -device usb-tablet \
    -serial pty \
    -qmp unix:"$QMP_SOCK",server,nowait \
    -boot menu=on \
    $EXTRA_ARGS &
QEMU_PID=$!

echo "QEMU started (PID: $QEMU_PID)"

# Wait for QMP socket to appear
echo -n "Waiting for QMP socket..."
for i in $(seq 1 30); do
    if [ -S "$QMP_SOCK" ]; then
        echo " ready"
        break
    fi
    echo -n "."
    sleep 0.5
done

if [ ! -S "$QMP_SOCK" ]; then
    echo " ERROR: QMP socket not created"
    exit 1
fi

# ── Start remote input server ────────────────────────────────
if [ "$START_REMOTE" = "1" ]; then
    echo "Starting remote input server on port $REMOTE_PORT..."
    python3 main.py --qmp "$QMP_SOCK" --remote --port "$REMOTE_PORT" &
    REMOTE_PID=$!
    echo "Remote input server started (PID: $REMOTE_PID)"
fi

# ── Start local input capture ────────────────────────────────
# Uncomment to auto-start local capture:
# python3 main.py --qmp "$QMP_SOCK" &

# ── Start clipboard sync ────────────────────────────────────
if [ "$START_CLIPBOARD" = "1" ]; then
    if [ ! -x "$CLIP98_BIN" ]; then
        echo "Downloading clip98..."
        curl -LO https://github.com/giulioz/clip98/releases/download/latest/"$CLIP98_BIN"
        chmod +x "$CLIP98_BIN"
        # Verify it's a real binary (not a redirect/error page)
        if [ "$(file "$CLIP98_BIN" 2>/dev/null | grep -c 'Mach-O\|ELF\|PE32\|executable')" -eq 0 ]; then
            echo "ERROR: Downloaded file is not a valid binary. It may be a redirect page."
            rm -f "$CLIP98_BIN"
            START_CLIPBOARD=0
        fi
    fi
    if [ "$START_CLIPBOARD" = "1" ]; then
        echo "Starting clip98 clipboard sync..."
        ./"$CLIP98_BIN" &
        CLIP98_PID=$!
        echo "clip98 started (PID: $CLIP98_PID)"
    fi
fi

# ── Wait for QEMU to exit ────────────────────────────────────
echo "Press Ctrl+C to stop everything"
wait $QEMU_PID 2>/dev/null || true

# ── Cleanup ──────────────────────────────────────────────────
echo "QEMU exited. Cleaning up..."
[ -n "$REMOTE_PID" ] && kill $REMOTE_PID 2>/dev/null
[ -n "$CLIP98_PID" ] && kill $CLIP98_PID 2>/dev/null
rm -f "$QMP_SOCK"
echo "Done."
