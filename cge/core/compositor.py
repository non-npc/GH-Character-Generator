from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

from .schema import SheetSpec
from .catalog import Catalog, ItemDef, get_variant_sheet_paths
from .util_images import load_rgba, extract_cell, hflip


@dataclass
class LayerResolved:
    layer: int
    name: str
    left_path: Path
    right_path: Optional[Path] = None


def resolve_layers(cat: Catalog, body_id: str, selections: Dict[str, Optional[Tuple[str, str]]]) -> List[LayerResolved]:
    # selections: slot -> (item_id, variant_id) or None
    layers: List[LayerResolved] = []
    for slot, sel in selections.items():
        if not sel:
            continue
        item_id, variant_id = sel
        item: Optional[ItemDef] = cat.items.get(slot, {}).get(item_id)
        if not item:
            continue
        left, right = get_variant_sheet_paths(item, variant_id, body_id)
        if not left and not right:
            continue
        left_path = left or right
        layers.append(LayerResolved(layer=int(item.layer), name=f"{slot}:{item_id}:{variant_id}", left_path=left_path, right_path=right))
    layers.sort(key=lambda x: x.layer)
    return layers


def compose_frame(
    sheet_spec: SheetSpec,
    base_left: Path,
    base_right: Optional[Path],
    layers: List[LayerResolved],
    direction: str,
    row: int,
    col: int,
    use_explicit_right: bool = True,
    flip_fallback: bool = True,
) -> Image.Image:
    cell_w, cell_h = sheet_spec.cell_w, sheet_spec.cell_h

    if col >= sheet_spec.frames_for_row(row):
        return Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))

    frame = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))

    # Split layers: behind body (layer < 0) vs in front (layer >= 0)
    behind_layers = [lyr for lyr in layers if lyr.layer < 0]
    front_layers = [lyr for lyr in layers if lyr.layer >= 0]
    behind_layers.sort(key=lambda x: x.layer)
    front_layers.sort(key=lambda x: x.layer)

    # Draw back items (backpacks, etc.) behind the body
    for lyr in behind_layers:
        if direction == "right" and use_explicit_right and lyr.right_path is not None:
            sheet = load_rgba(str(lyr.right_path))
            cell = extract_cell(sheet, col, row, cell_w, cell_h)
        else:
            sheet = load_rgba(str(lyr.left_path))
            cell = extract_cell(sheet, col, row, cell_w, cell_h)
            if direction == "right" and flip_fallback and (lyr.right_path is None or not use_explicit_right):
                cell = hflip(cell)
        frame.alpha_composite(cell)

    # Base body
    if direction == "right" and use_explicit_right and base_right is not None:
        base_sheet = load_rgba(str(base_right))
        base_cell = extract_cell(base_sheet, col, row, cell_w, cell_h)
    else:
        base_sheet = load_rgba(str(base_left))
        base_cell = extract_cell(base_sheet, col, row, cell_w, cell_h)
        if direction == "right" and flip_fallback and (base_right is None or not use_explicit_right):
            base_cell = hflip(base_cell)

    frame.alpha_composite(base_cell)

    # Front layers (clothing, cosmetics on top of body)
    for lyr in front_layers:
        if direction == "right" and use_explicit_right and lyr.right_path is not None:
            sheet = load_rgba(str(lyr.right_path))
            cell = extract_cell(sheet, col, row, cell_w, cell_h)
        else:
            sheet = load_rgba(str(lyr.left_path))
            cell = extract_cell(sheet, col, row, cell_w, cell_h)
            if direction == "right" and flip_fallback and (lyr.right_path is None or not use_explicit_right):
                cell = hflip(cell)
        frame.alpha_composite(cell)

    return frame


def compose_sheet(
    sheet_spec: SheetSpec,
    base_left: Path,
    base_right: Optional[Path],
    layers: List[LayerResolved],
    direction: str,
    use_explicit_right: bool = True,
    flip_fallback: bool = True,
) -> Image.Image:
    w = sheet_spec.cols * sheet_spec.cell_w
    h = sheet_spec.rows * sheet_spec.cell_h
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    for r in range(sheet_spec.rows):
        for c in range(sheet_spec.cols):
            cell = compose_frame(sheet_spec, base_left, base_right, layers, direction, r, c, use_explicit_right, flip_fallback)
            out.alpha_composite(cell, (c * sheet_spec.cell_w, r * sheet_spec.cell_h))

    return out
