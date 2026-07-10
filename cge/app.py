from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main(assets_root: Path | None = None) -> int:
    app = QApplication(sys.argv)
    if assets_root is None:
        assets_root = Path.cwd() / "assets"
    win = MainWindow(assets_root=assets_root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
