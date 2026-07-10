from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .schema import SheetSpec
from .util_paths import resolve_assets_root


@dataclass
class SlotSelection:
    item: str
    variant: str


@dataclass
class CGEProject:
    cge_version: int = 1
    assets_root: str = "./assets"
    sheet: SheetSpec = field(default_factory=SheetSpec.canonical)
    body: str = ""
    body_base: str = "base"  # base variant: "base" or e.g. "demons", "zombies"
    direction: str = "left"  # left|right
    slots: Dict[str, Optional[SlotSelection]] = field(default_factory=dict)
    options: Dict = field(default_factory=lambda: {
        "use_explicit_right_if_available": True,
        "fallback_flip_for_right": True,
        "missing_asset_policy": "warn",  # warn|disable|error
    })

    def to_json(self) -> Dict:
        return {
            "cge_version": self.cge_version,
            "assets_root": self.assets_root,
            "sheet": self.sheet.to_json(),
            "character": {
                "body": self.body,
                "body_base": self.body_base,
                "direction": self.direction,
                "slots": {
                    k: (None if v is None else {"item": v.item, "variant": v.variant})
                    for k, v in self.slots.items()
                },
            },
            "options": self.options,
        }

    @staticmethod
    def from_json(d: Dict) -> "CGEProject":
        p = CGEProject()
        p.cge_version = int(d.get("cge_version", 1))
        p.assets_root = d.get("assets_root", "./assets")
        p.sheet = SheetSpec.from_json(d.get("sheet", {}) or {})
        ch = d.get("character", {}) or {}
        p.body = ch.get("body", "")
        p.body_base = ch.get("body_base", "base")
        p.direction = ch.get("direction", "left")
        slots = ch.get("slots", {}) or {}
        out = {}
        for slot, sel in slots.items():
            if sel is None:
                out[slot] = None
            else:
                out[slot] = SlotSelection(item=str(sel.get("item", "")), variant=str(sel.get("variant", "")))
        p.slots = out
        p.options = d.get("options", p.options) or p.options
        return p

    @staticmethod
    def load(path: Path) -> "CGEProject":
        d = json.loads(path.read_text(encoding="utf-8"))
        return CGEProject.from_json(d)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    def resolved_assets_root(self, project_path: Optional[Path]) -> Path:
        return resolve_assets_root(project_path, self.assets_root)
