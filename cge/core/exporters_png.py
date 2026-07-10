from __future__ import annotations

from pathlib import Path

from .schema import SheetSpec
from .compositor import compose_sheet, LayerResolved


def export_png_sheet(
    out_path: Path,
    sheet_spec: SheetSpec,
    base_left: Path,
    base_right: Path | None,
    layers: list[LayerResolved],
    direction: str,
    use_explicit_right: bool = True,
    flip_fallback: bool = True,
) -> None:
    img = compose_sheet(sheet_spec, base_left, base_right, layers, direction, use_explicit_right, flip_fallback)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
