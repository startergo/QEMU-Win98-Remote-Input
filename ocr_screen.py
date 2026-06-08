"""
OCR-based screen state recognition for macOS recovery console.

Requires: tesseract (CLI), Pillow
Optional: if unavailable, falls back to manual prompting.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path


class OCRScreen:
    """Reads the QEMU display to detect macOS recovery GUI states."""

    # Recognized screen states
    LANGUAGE_PICKER = "language"      # "Language" / "English" visible
    UTILITIES_MENU = "utilities"      # "Utilities" menu bar visible
    TERMINAL_READY = "terminal"       # Terminal prompt visible
    UNKNOWN        = "unknown"

    def __init__(self, qmp, tesseract_cmd="tesseract"):
        self.qmp = qmp
        self.tesseract_cmd = tesseract_cmd
        self._has_tesseract = shutil.which(tesseract_cmd) is not None
        self._tmpdir = tempfile.mkdtemp(prefix="qemu-ocr-")

    @property
    def available(self):
        return self._has_tesseract

    def capture_and_recognize(self):
        """Take a screenshot and return the detected screen state."""
        if not self._has_tesseract:
            return self.UNKNOWN

        img_path = Path(self._tmpdir) / "screen.png"
        self.qmp.screenshot(img_path)

        result = subprocess.run(
            [self.tesseract_cmd, str(img_path), "stdout",
             "--psm", "11", "--dpi", "72", "-l", "eng"],
            capture_output=True, text=True, timeout=10
        )
        text = result.stdout

        if any(w in text for w in ("Language", "English", "Fran")):
            return self.LANGUAGE_PICKER
        if "Utilities" in text:
            return self.UTILITIES_MENU
        if any(w in text for w in ("Terminal", "Shell", "sh-")):
            return self.TERMINAL_READY
        return self.UNKNOWN

    def wait_for_state(self, target_state, timeout=300, poll_interval=5):
        """Poll until a specific screen state is detected or timeout."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.capture_and_recognize()
            if state == target_state:
                return True
            time.sleep(poll_interval)
        return False

    def read_text(self, psm=6):
        """Capture the guest screen and return OCR'd text.

        Args:
            psm: Tesseract page segmentation mode.
                 6 = uniform block (good for terminal / app output)
                 11 = sparse text (good for GUI with scattered labels)

        Returns:
            Recognized text as a string, or empty string if tesseract
            is unavailable.
        """
        if not self._has_tesseract:
            return ""
        img_path = Path(self._tmpdir) / "screen.png"
        self.qmp.screenshot(img_path)
        result = subprocess.run(
            [self.tesseract_cmd, str(img_path), "stdout",
             "--psm", str(psm), "--dpi", "72", "-l", "eng"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout

    def cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()
