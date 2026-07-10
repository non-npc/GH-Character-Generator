from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from apng import APNG

from .schema import SheetSpec
from .compositor import compose_frame, LayerResolved


DEFAULT_FPS = {
    "idle": 8, "walk": 12, "run": 16, "jump": 12, "fall": 12, "swing": 14, "die": 10
}
DEFAULT_LOOP = {
    "idle": True, "walk": True, "run": True, "jump": False, "fall": False, "swing": False, "die": False
}


def export_apng_actions(
    out_dir: Path,
    project_name: str,
    sheet_spec: SheetSpec,
    base_left: Path,
    base_right: Path | None,
    layers: list[LayerResolved],
    direction: str,
    fps: Optional[Dict[str, int]] = None,
    loop: Optional[Dict[str, bool]] = None,
    use_explicit_right: bool = True,
    flip_fallback: bool = True,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = fps or DEFAULT_FPS
    loop = loop or DEFAULT_LOOP
    paths: list[Path] = []

    for row in range(sheet_spec.rows):
        action = sheet_spec.action_for_row(row)
        n = sheet_spec.frames_for_row(row)

        apng = APNG()
        delay_den = max(1, int(fps.get(action, 12)))  # frames per second
        for col in range(n):
            fr = compose_frame(sheet_spec, base_left, base_right, layers, direction, row, col, use_explicit_right, flip_fallback)
            import io
            buf = io.BytesIO()
            fr.save(buf, format="PNG")
            buf.seek(0)
            apng.append_file(buf, delay=1, delay_den=delay_den)

        out_path = out_dir / f"{project_name}__{direction}__{action}.apng"
        num_plays = 0 if loop.get(action, True) else 1
        apng.save(out_path, num_plays=num_plays)
        paths.append(out_path)

    return paths
