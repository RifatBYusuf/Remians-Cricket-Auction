from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps


ALLOWED_IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return result or "asset"


def validate_image(name: str, mime: str, content: bytes) -> tuple[str, tuple[int, int]]:
    if mime not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"{name}: use a PNG, JPG or WebP image.")
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError(f"{name}: image must be between 1 byte and 10 MB.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
    except Exception as exc:
        raise ValueError(f"{name}: the file is not a valid image.") from exc
    if width < 100 or height < 100 or width > 8000 or height > 8000:
        raise ValueError(f"{name}: dimensions must be between 100 and 8,000 pixels.")
    return ALLOWED_IMAGE_TYPES[mime], (width, height)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_player_card(photo_bytes: bytes, name: str, role: str, base_price: int | None) -> bytes:
    """Create a polished 4:5 PNG card while preserving the photo crop."""
    canvas = Image.new("RGB", (1200, 1500), "#F7FAFC")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1200, 185), fill="#173B70")
    draw.rectangle((0, 1400, 1200, 1500), fill="#159447")
    draw.rectangle((0, 185, 22, 1400), fill="#E63946")
    with Image.open(BytesIO(photo_bytes)) as source:
        photo = ImageOps.exif_transpose(source).convert("RGB")
        fitted = ImageOps.fit(photo, (900, 900), method=Image.Resampling.LANCZOS)
    canvas.paste(fitted, (150, 245))
    draw.rounded_rectangle((115, 210, 1085, 1180), radius=32, outline="#DDE7F1", width=10)
    draw.text((600, 75), "REMIANS AUSTRALIA", font=_font(54, True), anchor="mm", fill="white")
    draw.text((600, 1240), name.strip().upper(), font=_font(68, True), anchor="mm", fill="#12233F")
    draw.text((600, 1325), role.strip(), font=_font(40), anchor="mm", fill="#355675")
    if base_price:
        draw.text((600, 1448), f"BASE  ৳{base_price:,}", font=_font(38, True), anchor="mm", fill="white")
    else:
        draw.text((600, 1448), "CRICKET PLAYER AUCTION", font=_font(34, True), anchor="mm", fill="white")
    output = BytesIO()
    canvas.save(output, "PNG", optimize=True)
    return output.getvalue()

