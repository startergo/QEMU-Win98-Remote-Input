#!/bin/sh
# ──────────────────────────────────────────────────────────────
# launch-macos-recovery.sh — Launch QEMU with macOS recovery media
#
# Starts QEMU with QMP support and optional recovery automation.
# Modeled after launch-win98.sh.
#
# Usage:
#   ./launch-macos-recovery.sh                     # Start VM with QMP
#   ./launch-macos-recovery.sh --iso payload.iso   # Start + auto recovery
#   ./launch-macos-recovery.sh --manual            # Manual mode (no auto)
#   ./launch-macos-recovery.sh --headless          # No display
# ──────────────────────────────────────────────────────────────

set -e

# ── Resolve script directory ────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Configuration ────────────────────────────────────────────
QMP_SOCK="/tmp/qemu-macos.sock"
DISK="macos.qcow2"
INSTALLER=""
SCRIPT_ISO=""
VOLUME_ID="MACROS"
RAM_MB=4096
MANUAL=0
EXTRA_ARGS=""

# ── Parse arguments ──────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --disk)       shift; DISK="$1" ;;
        --installer)  shift; INSTALLER="$1" ;;
        --iso)        shift; SCRIPT_ISO="$1" ;;
        --volume-id)  shift; VOLUME_ID="$1" ;;
        --ram)        shift; RAM_MB="$1" ;;
        --manual)     MANUAL=1 ;;
        --headless)   EXTRA_ARGS="$EXTRA_ARGS -display none" ;;
        --vnc)        EXTRA_ARGS="$EXTRA_ARGS -display vnc=:1" ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--disk path] [--installer path] [--iso path] [--volume-id label] [--ram MB] [--manual] [--headless] [--vnc]" >&2
            exit 1
            ;;
    esac
    shift
done

# ── Cleanup old QMP socket ───────────────────────────────────
rm -f "$QMP_SOCK"

# ── Start QEMU ───────────────────────────────────────────────
echo "Starting QEMU: macOS Recovery"
echo "QMP socket: $QMP_SOCK"
echo "RAM: ${RAM_MB}MB"

# Build QEMU command as an array — avoids eval and shell injection
QEMU_CMD=(
    qemu-system-x86_64
    -nodefaults
    -rtc base=localtime
    -display sdl
    -monitor stdio
    -name "macOS Recovery"
    -M q35,accel=hvf
    -cpu host
    -m "$RAM_MB"
    -device VGA
    -device virtio-net-pci,rombar=0
    -device ich9-usb-ehci1
    -device usb-kbd
    -device usb-tablet
    -drive id=macos,if=virtio,file="$DISK"
)

[ -n "$INSTALLER" ] && QEMU_CMD+=(
    -drive id=installer,if=none,file="$INSTALLER"
    -device ide-cd,drive=installer
)
[ -n "$SCRIPT_ISO" ] && QEMU_CMD+=(
    -drive id=scripts,if=none,media=cdrom,file="$SCRIPT_ISO"
    -device ide-cd,drive=scripts
)

QEMU_CMD+=(
    -qmp "unix:$QMP_SOCK,server,nowait"
)
# shellcheck disable=SC2086 — EXTRA_ARGS is intentionally word-split
[ -n "$EXTRA_ARGS" ] && QEMU_CMD+=($EXTRA_ARGS)

"${QEMU_CMD[@]}" &

QEMU_PID=$!
echo "QEMU started (PID: $QEMU_PID)"

# ── Wait for QMP socket ──────────────────────────────────────
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
    echo " ERROR: QMP socket not created" >&2
    exit 1
fi

# ── Auto-start recovery automation ───────────────────────────
if [ "$MANUAL" -eq 0 ] && [ -n "$SCRIPT_ISO" ]; then
    echo "Starting recovery automation..."
    python3 "$SCRIPT_DIR/main.py" --qmp "$QMP_SOCK" install \
        --iso "$SCRIPT_ISO" --volume-id "$VOLUME_ID"
fi

# ── Wait for QEMU to exit ────────────────────────────────────
echo "Press Ctrl+C to stop"
wait $QEMU_PID 2>/dev/null || true

# ── Cleanup ──────────────────────────────────────────────────
echo "QEMU exited. Cleaning up..."
rm -f "$QMP_SOCK"
echo "Done."
