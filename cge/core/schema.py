from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ActionSpec:
    action: str
    frames: int


@dataclass(frozen=True)
class SheetSpec:
    rows: int = 7
    cols: int = 10
    cell_w: int = 80
    cell_h: int = 64
    row_actions: List[ActionSpec] = None

    @staticmethod
    def canonical() -> "SheetSpec":
        return SheetSpec(
            rows=7,
            cols=10,
            cell_w=80,
            cell_h=64,
            row_actions=[
                ActionSpec("idle", 5),
                ActionSpec("walk", 8),
                ActionSpec("run", 8),
                ActionSpec("jump", 4),
                ActionSpec("fall", 4),
                ActionSpec("swing", 6),
                ActionSpec("die", 10),
            ],
        )

    def frames_for_row(self, row: int) -> int:
        return self.row_actions[row].frames

    def action_for_row(self, row: int) -> str:
        return self.row_actions[row].action

    def row_for_action(self, action: str) -> int:
        for i, a in enumerate(self.row_actions):
            if a.action == action:
                return i
        raise KeyError(action)

    def to_json(self) -> Dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cell_w": self.cell_w,
            "cell_h": self.cell_h,
            "row_actions": [{"action": a.action, "frames": a.frames} for a in self.row_actions],
        }

    @staticmethod
    def from_json(d: Dict) -> "SheetSpec":
        ra = [ActionSpec(x["action"], int(x["frames"])) for x in d.get("row_actions", [])]
        if not ra:
            return SheetSpec.canonical()
        return SheetSpec(
            rows=int(d.get("rows", 7)),
            cols=int(d.get("cols", 10)),
            cell_w=int(d.get("cell_w", 80)),
            cell_h=int(d.get("cell_h", 64)),
            row_actions=ra,
        )
