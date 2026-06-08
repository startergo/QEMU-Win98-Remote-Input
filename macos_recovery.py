"""
macOS Recovery Console automation for QEMU.

Orchestrates: screen navigation -> terminal access -> script execution.
Modeled after macos-virtualbox's prompt_lang_utils_terminal() and
populate_bootable_installer_virtual_disk().
"""

import time

from ocr_screen import OCRScreen


class MacOSRecovery:
    """Automate macOS recovery console operations in a QEMU VM."""

    def __init__(self, qmp):
        self.qmp = qmp
        self.ocr = OCRScreen(qmp)

    def cleanup(self):
        """Release resources (OCR temp directory)."""
        self.ocr.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    # -- Navigation --------------------------------------------------------

    def navigate_to_terminal(self, auto=True):
        """Navigate from recovery boot to an open Terminal window.

        Args:
            auto: If True and tesseract is available, use OCR to
                  automatically detect screen states. If False or
                  OCR unavailable, prompt the user to press Enter.
        """
        if auto and self.ocr.available:
            self._auto_navigate_to_terminal()
        else:
            self._manual_navigate_to_terminal()

    def _auto_navigate_to_terminal(self, timeout=300):
        """OCR-driven navigation: Language -> Utilities -> Terminal."""
        poll = 5  # seconds between OCR attempts

        for _ in range(timeout // poll):
            state = self.ocr.capture_and_recognize()

            if state == OCRScreen.LANGUAGE_PICKER:
                print("  Detected: Language picker -- pressing Enter")
                self.qmp.press_enter()
                time.sleep(20)  # wait for utilities to load

            elif state == OCRScreen.UTILITIES_MENU:
                print("  Detected: Utilities menu -- opening Terminal")
                self.qmp.navigate_menu('u', 't')
                # Let the OCR poll confirm TERMINAL_READY; no fixed sleep

            elif state == OCRScreen.TERMINAL_READY:
                print("  Detected: Terminal prompt ready")
                return True

            else:
                time.sleep(poll)

        print("  OCR navigation timed out, falling back to manual")
        self._manual_navigate_to_terminal()

    def _manual_navigate_to_terminal(self):
        """Manual navigation with user prompts."""
        input("Press Enter when the Language window is ready...")
        self.qmp.press_enter()
        input("Press Enter when the macOS Utilities window is ready...")
        self.qmp.navigate_menu('u', 't')
        input("Press Enter when the Terminal prompt is ready...")

    # -- Terminal Management ------------------------------------------------

    def open_another_terminal(self):
        """Open a new Terminal window (Cmd+N)."""
        self.qmp.send_key_combo(["meta_l", "n"])
        time.sleep(1)

    def cycle_terminals(self):
        """Switch to the next Terminal window (Cmd+`)."""
        self.qmp.send_key_combo(["meta_l", "grave_accent"])
        time.sleep(1)

    # -- Script Execution ---------------------------------------------------

    def run_script_from_iso(self, iso_path, script_name, volume_id):
        """Type the path to a script on a mounted ISO and execute it.

        Args:
            iso_path: path to the ISO file (for future hot-plug support)
            script_name: filename of the script inside the ISO
            volume_id: volume label (becomes /Volumes/<volume_id>/)
        """
        path = f"/Volumes/{volume_id}/{script_name}"
        print(f"  Typing: {path}")
        self.qmp.type_string(path, delay=0.02)
        time.sleep(0.2)
        self.qmp.press_enter()

    # -- High-Level Workflows -----------------------------------------------

    def populate_installer_disk(self, iso_path, volume_id, script_name):
        """Full workflow: navigate to terminal -> run installer script.

        Mirrors macos-virtualbox's populate_bootable_installer_virtual_disk().
        """
        print("Navigating to Terminal...")
        self.navigate_to_terminal()

        print(f"Running {script_name} from ISO...")
        self.run_script_from_iso(iso_path, script_name, volume_id)

        print("Script launched. Monitor VM for completion.")

    def install_macos(self, iso_path, volume_id):
        """Full workflow: two terminals for concurrent NVRAM + installer.

        Mirrors macos-virtualbox's populate_macos_target_disk():
          Terminal 1: runs startosinstall.sh (installer)
          Terminal 2: runs nvram.sh (waits for installer, copies EFI)
        """
        print("Navigating to Terminal...")
        self.navigate_to_terminal()

        # Open second terminal for the NVRAM watcher
        print("Opening second terminal for NVRAM watcher...")
        self.open_another_terminal()

        print("Running NVRAM watcher in Terminal 2...")
        self.run_script_from_iso(iso_path, "nvram.sh", volume_id)

        # Switch back to Terminal 1 for the installer
        print("Switching to Terminal 1 for installer...")
        self.cycle_terminals()

        print("Running macOS installer in Terminal 1...")
        self.run_script_from_iso(iso_path, "startosinstall.sh", volume_id)

        print("Installer launched. macOS will install and reboot.")

    # -- Interactive Typing -------------------------------------------------

    def interactive(self):
        """Read lines from stdin and type them into the guest Terminal.

        Provides an interactive shell-like experience where each line typed
        on the host is forwarded to the guest via QMP type_string.
        Press Ctrl+C or type 'exit' to quit.
        """
        print("Interactive mode — type commands, they appear in the guest.")
        print("Press Ctrl+C or type 'exit' to quit.")
        try:
            while True:
                try:
                    line = input("guest> ")
                except EOFError:
                    break
                if line.strip().lower() == "exit":
                    break
                if not line.strip():
                    continue
                self.qmp.type_string(line, delay=0.02)
                self.qmp.press_enter()
        except KeyboardInterrupt:
            print()
