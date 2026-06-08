"""
Build ISO images containing shell scripts for macOS recovery automation.

Requires: genisoimage or mkisofs or xorrisofs (any one)
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _find_mkisofs():
    """Find an available ISO creation tool."""
    for cmd in ("genisoimage", "mkisofs", "xorrisofs"):
        path = shutil.which(cmd)
        if path:
            return path
    raise FileNotFoundError(
        "No ISO creation tool found. Install genisoimage, mkisofs, or xorrisofs."
    )


def build_script_iso(scripts, iso_path, volume_id="MACROS"):
    """Create an ISO image containing shell scripts.

    Args:
        scripts: dict of {filename: content_string}
        iso_path: output ISO file path
        volume_id: volume label (appears as /Volumes/<label> in macOS)

    Returns:
        Path to the created ISO file.
    """
    mkisofs = _find_mkisofs()

    with tempfile.TemporaryDirectory(prefix="qemu-iso-") as tmp:
        for name, content in scripts.items():
            filepath = os.path.join(tmp, name)
            with open(filepath, "w") as f:
                f.write(content)
            os.chmod(filepath, 0o755)

        cmd = [
            mkisofs,
            "-o", str(iso_path),
            "-V", volume_id,
            "-R",           # Rock Ridge extensions (preserves filenames)
            "-J",           # Joliet extensions (Windows compatibility)
            "-input-charset", "utf-8",
            tmp,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    return Path(iso_path)
