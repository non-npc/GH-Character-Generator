from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _norm(s: str) -> str:
    return (s or "").strip().lower()


@dataclass
class VariantDef:
    variant_id: str
    body_left: Dict[str, Path] = field(default_factory=dict)   # normalized body_id -> path
    body_right: Dict[str, Path] = field(default_factory=dict)  # normalized body_id -> path
    meta: Dict = field(default_factory=dict)


@dataclass
class ItemDef:
    item_id: str
    slot: str
    layer: int
    source: str  # "wearables" or "cosmetics"
    excludes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    supported_bodies: Optional[List[str]] = None
    variants: Dict[str, VariantDef] = field(default_factory=dict)
    meta: Dict = field(default_factory=dict)


@dataclass
class BodyDef:
    body_id: str
    base_left: Path
    base_right: Optional[Path] = None
    preview: Optional[Path] = None
    base_variants: Dict[str, Tuple[Path, Optional[Path]]] = field(default_factory=dict)  # variant_id -> (left, right)


@dataclass
class Catalog:
    assets_root: Path
    bodies: Dict[str, BodyDef] = field(default_factory=dict)  # normalized body_id -> BodyDef
    items: Dict[str, Dict[str, ItemDef]] = field(default_factory=dict)  # slot -> item_id -> ItemDef

    def all_slots(self) -> List[str]:
        return sorted(self.items.keys())


def get_body_base_paths(cat: Catalog, body_id: str, base_variant: str) -> Tuple[Path, Optional[Path]]:
    """Return (base_left, base_right) for the given body and base variant. base_variant 'base' or 'default' uses the default base."""
    body_id = _norm(body_id)
    b = cat.bodies.get(body_id)
    if not b:
        return (Path(), None)
    base_variant = (base_variant or "base").strip().lower()
    if base_variant in ("base", "default", ""):
        return (b.base_left, b.base_right)
    return b.base_variants.get(base_variant, (b.base_left, b.base_right))


def _read_json(p: Path) -> Dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def scan_catalog(assets_root: Path) -> Catalog:
    assets_root = Path(assets_root).resolve()
    cat = Catalog(assets_root=assets_root)

    # Bodies
    bodies_dir = assets_root / "bodies"
    if bodies_dir.exists():
        for body_dir in sorted([p for p in bodies_dir.iterdir() if p.is_dir()]):
            body_id = _norm(body_dir.name)
            base_left = body_dir / "base.png"
            if not base_left.exists():
                continue
            base_right = body_dir / "base_right.png"
            preview = body_dir / "preview.png"
            base_variants: Dict[str, Tuple[Path, Optional[Path]]] = {}
            for png in sorted(body_dir.glob("*.png")):
                stem = png.stem
                if stem == "preview" or stem.endswith("_right"):
                    continue
                if stem == "base":
                    continue
                right_png = body_dir / f"{stem}_right.png"
                base_variants[stem] = (png, right_png if right_png.exists() else None)
            cat.bodies[body_id] = BodyDef(
                body_id=body_id,
                base_left=base_left,
                base_right=base_right if base_right.exists() else None,
                preview=preview if preview.exists() else None,
                base_variants=base_variants,
            )

    # Body-specific clothing: wearables/<body_clothing>/<slot>/*.png
    # e.g. male_clothing/torso/, female_clothing/legs/, etc.
    _BODY_CLOTHING_MAP = {"male_clothing": "male", "female_clothing": "female"}
    _SLOT_LAYERS = {"back": -10, "feet": 15, "hands": 25, "head": 35, "items": 30, "legs": 10, "torso": 20}
    wearables_dir = assets_root / "wearables"
    if wearables_dir.exists():
        for folder_name in ("male_clothing", "female_clothing"):
            clothing_dir = wearables_dir / folder_name
            if not clothing_dir.is_dir():
                continue
            body_id = _norm(_BODY_CLOTHING_MAP[folder_name])
            for slot_dir in sorted([p for p in clothing_dir.iterdir() if p.is_dir()]):
                slot = slot_dir.name
                layer = _SLOT_LAYERS.get(slot, 20)
                for png in sorted(slot_dir.glob("*.png")):
                    stem = png.stem
                    if stem.endswith("_right"):
                        continue
                    item_id = stem
                    if not item_id.strip():
                        continue
                    right_png = slot_dir / f"{stem}_right.png"
                    item = cat.items.get(slot, {}).get(item_id)
                    if item is None:
                        var = VariantDef(variant_id="default", meta={})
                        item = ItemDef(
                            item_id=item_id,
                            slot=slot,
                            layer=layer,
                            source="wearables",
                            meta={"id": item_id, "slot": slot},
                        )
                        item.variants["default"] = var
                        cat.items.setdefault(slot, {})[item_id] = item
                    var = item.variants["default"]
                    var.body_left[body_id] = png
                    if right_png.exists():
                        var.body_right[body_id] = right_png

    # Body-specific cosmetics: cosmetics/<body_cosmetics>/<slot>/...
    # Flat: <slot>/<item>.png  OR  with variants: <slot>/<item>/<variant>.png
    _BODY_COSMETICS_MAP = {"male_cosmetics": "male", "female_cosmetics": "female"}
    _COSMETIC_SLOT_LAYERS = {"ears": 28, "eyes": 29, "face": 33, "facial_hair": 31, "hair": 30, "hands": 27, "jewelry": 26, "nose": 32}
    cosmetics_dir = assets_root / "cosmetics"
    if cosmetics_dir.exists():
        for folder_name in ("male_cosmetics", "female_cosmetics"):
            cosmetics_subdir = cosmetics_dir / folder_name
            if not cosmetics_subdir.is_dir():
                continue
            body_id = _norm(_BODY_COSMETICS_MAP[folder_name])
            for slot_dir in sorted([p for p in cosmetics_subdir.iterdir() if p.is_dir()]):
                slot = slot_dir.name
                layer = _COSMETIC_SLOT_LAYERS.get(slot, 30)
                for entry in sorted(slot_dir.iterdir()):
                    if entry.is_file() and entry.suffix.lower() == ".png":
                        stem = entry.stem
                        if stem.endswith("_right"):
                            continue
                        item_id = stem
                        if not item_id.strip():
                            continue
                        right_png = slot_dir / f"{stem}_right.png"
                        item = cat.items.get(slot, {}).get(item_id)
                        if item is None:
                            var = VariantDef(variant_id="default", meta={})
                            item = ItemDef(
                                item_id=item_id,
                                slot=slot,
                                layer=layer,
                                source="cosmetics",
                                meta={"id": item_id, "slot": slot},
                            )
                            item.variants["default"] = var
                            cat.items.setdefault(slot, {})[item_id] = item
                        var = item.variants["default"]
                        var.body_left[body_id] = entry
                        if right_png.exists():
                            var.body_right[body_id] = right_png
                    elif entry.is_dir():
                        item_id = entry.name
                        for png in sorted(entry.glob("*.png")):
                            stem = png.stem
                            if stem.endswith("_right"):
                                continue
                            variant_id = stem
                            if not variant_id.strip():
                                continue
                            right_png = entry / f"{stem}_right.png"
                            item = cat.items.get(slot, {}).get(item_id)
                            if item is None:
                                item = ItemDef(
                                    item_id=item_id,
                                    slot=slot,
                                    layer=layer,
                                    source="cosmetics",
                                    meta={"id": item_id, "slot": slot},
                                )
                                cat.items.setdefault(slot, {})[item_id] = item
                            var = item.variants.get(variant_id)
                            if var is None:
                                var = VariantDef(variant_id=variant_id, meta={})
                                item.variants[variant_id] = var
                            var.body_left[body_id] = png
                            if right_png.exists():
                                var.body_right[body_id] = right_png

    # Items: nested wearables and cosmetics (slot/item/variant structure, legacy)
    for source in ("wearables", "cosmetics"):
        src_dir = assets_root / source
        if not src_dir.exists():
            continue

        for slot_dir in sorted([p for p in src_dir.iterdir() if p.is_dir()]):
            slot = slot_dir.name
            if slot in ("male_clothing", "female_clothing") and source == "wearables":
                continue
            if slot in ("male_cosmetics", "female_cosmetics") and source == "cosmetics":
                continue
            for item_dir in sorted([p for p in slot_dir.iterdir() if p.is_dir()]):
                item_id = item_dir.name
                item_meta = _read_json(item_dir / "meta.json")
                default_layer = -10 if slot == "back" and source == "wearables" else 0
                layer = int(item_meta.get("layer", default_layer))
                excludes = list(item_meta.get("excludes", []) or [])
                tags = list(item_meta.get("tags", []) or [])
                supported_bodies = item_meta.get("supported_bodies", None)

                item = ItemDef(
                    item_id=item_id,
                    slot=str(item_meta.get("slot", slot)),
                    layer=layer,
                    source=source,
                    excludes=excludes,
                    tags=tags,
                    supported_bodies=supported_bodies,
                    meta=item_meta,
                )

                for vdir in sorted([p for p in item_dir.iterdir() if p.is_dir()]):
                    variant_id = vdir.name
                    vmeta = _read_json(vdir / "meta.json")
                    var = VariantDef(variant_id=variant_id, meta=vmeta)

                    for png in vdir.glob("*.png"):
                        stem = png.stem
                        if stem.endswith("_right"):
                            body = _norm(stem[:-6])
                            var.body_right[body] = png
                        else:
                            body = _norm(stem)
                            var.body_left[body] = png

                    item.variants[variant_id] = var

                cat.items.setdefault(item.slot, {})[item_id] = item

    return cat


def item_variant_supports_body(item: ItemDef, variant_id: str, body_id: str) -> bool:
    body_id = _norm(body_id)
    v = item.variants.get(variant_id)
    if not v:
        return False

    vb = v.meta.get("supported_bodies") if isinstance(v.meta, dict) else None
    if vb:
        return body_id in [_norm(b) for b in vb]

    if item.supported_bodies:
        if body_id not in [_norm(b) for b in item.supported_bodies]:
            return False

    return (body_id in v.body_left) or (body_id in v.body_right)


def get_variant_sheet_paths(item: ItemDef, variant_id: str, body_id: str) -> Tuple[Optional[Path], Optional[Path]]:
    body_id = _norm(body_id)
    v = item.variants.get(variant_id)
    if not v:
        return None, None
    return v.body_left.get(body_id), v.body_right.get(body_id)
