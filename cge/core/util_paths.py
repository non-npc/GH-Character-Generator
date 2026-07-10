from __future__ import annotations

from pathlib import Path


def resolve_assets_root(project_path: Path | None, assets_root_str: str) -> Path:
    # Resolve an assets_root string (often relative like './assets') against a project file location.
    # If project_path is None, resolve against current working directory.
    base = Path.cwd() if project_path is None else project_path.parent
    p = Path(assets_root_str)
    return p if p.is_absolute() else (base / p).resolve()


def safe_filename(s: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    out = []
    for ch in s:
        out.append(ch if ch in allowed else "_")
    return "".join(out).strip("_") or "export"
