"""Launch the GandalfHardcore Character Generator application from the project root."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is the working directory so assets/ is found
_PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(_PROJECT_ROOT)

# Use assets path relative to this script so it works regardless of launch context
_ASSETS_ROOT = (_PROJECT_ROOT / "assets").resolve()

from cge.app import main

if __name__ == "__main__":
    sys.exit(main(assets_root=_ASSETS_ROOT))
