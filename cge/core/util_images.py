from __future__ import annotations

from functools import lru_cache
from PIL import Image


@lru_cache(maxsize=256)
def load_rgba(path: str) -> Image.Image:
    return Image.open(path).convert("RGBA")


def extract_cell(sheet: Image.Image, col: int, row: int, cell_w: int, cell_h: int) -> Image.Image:
    x0 = col * cell_w
    y0 = row * cell_h
    return sheet.crop((x0, y0, x0 + cell_w, y0 + cell_h))


def hflip(img: Image.Image) -> Image.Image:
    return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def make_checkerboard(width: int, height: int, tile_size: int = 8, light: tuple = (0xC0, 0xC0, 0xC0), dark: tuple = (0x98, 0x98, 0x98)) -> Image.Image:
    """Create a Photoshop-style checkerboard background (light/dark gray tiles)."""
    from PIL import ImageDraw
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    for ty in range(0, height, tile_size):
        for tx in range(0, width, tile_size):
            if ((tx // tile_size) + (ty // tile_size)) % 2 == 0:
                color = (*light, 255)
            else:
                color = (*dark, 255)
            draw.rectangle([tx, ty, tx + tile_size, ty + tile_size], fill=color)
    return img
