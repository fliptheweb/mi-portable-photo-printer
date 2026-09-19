"""Prepare an image for the printer: exactly 1040 x 1560 px, baseline JPEG."""

from __future__ import annotations

import io

PRINT_W = 1040
PRINT_H = 1560


def prepare(source, fit: str = "cover", background=(255, 255, 255), quality: int = 90) -> bytes:
    """Return JPEG bytes sized 1040x1560.

    `source` is a path, raw bytes, or a PIL.Image. `fit`:
      - "cover"   : scale to fill, then centre-crop (no borders, may lose edges)
      - "contain" : scale to fit, pad with `background` (whole image kept)
      - "stretch" : ignore aspect ratio
    """
    from PIL import Image, ImageOps

    if isinstance(source, Image.Image):
        im = source
    elif isinstance(source, (bytes, bytearray)):
        im = Image.open(io.BytesIO(bytes(source)))
    else:
        im = Image.open(source)
    im = ImageOps.exif_transpose(im).convert("RGB")

    if fit == "cover":
        out = ImageOps.fit(im, (PRINT_W, PRINT_H), method=Image.LANCZOS, centering=(0.5, 0.5))
    elif fit == "contain":
        out = Image.new("RGB", (PRINT_W, PRINT_H), background)
        scaled = ImageOps.contain(im, (PRINT_W, PRINT_H), method=Image.LANCZOS)
        out.paste(scaled, ((PRINT_W - scaled.width) // 2, (PRINT_H - scaled.height) // 2))
    elif fit == "stretch":
        out = im.resize((PRINT_W, PRINT_H), Image.LANCZOS)
    else:
        raise ValueError(f"unknown fit mode {fit!r}")

    buf = io.BytesIO()
    # Baseline (non-progressive) JPEG with standard Huffman tables — what the printer expects.
    out.save(buf, format="JPEG", quality=quality, optimize=False, progressive=False)
    return buf.getvalue()
