"""
Local file storage service.
Later can swap to S3/R2 by replacing save_* functions.
"""

import uuid
import aiofiles
import cv2
import numpy as np
from pathlib import Path
from fastapi import UploadFile

from app.config import PAGE_DIR, GLYPH_DIR, MAX_UPLOAD_MB, ALLOWED_IMAGE_TYPES


class StorageError(Exception):
    pass


async def save_page_image(file: UploadFile, copybook_id: str, page_number: int) -> tuple[Path, int, int]:
    """
    Save an uploaded page image.
    Returns (saved_path, width, height).
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise StorageError(f"Unsupported file type: {file.content_type}")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise StorageError(f"File exceeds {MAX_UPLOAD_MB}MB limit")

    # Decode to get dimensions
    arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise StorageError("Cannot decode image")
    h, w = img.shape[:2]

    # Save as high-quality JPEG
    dest_dir = PAGE_DIR / copybook_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"page_{page_number:04d}.jpg"
    dest = dest_dir / filename

    cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

    return dest, w, h


def save_glyph_crop(crop: np.ndarray, copybook_id: str, character: str) -> Path:
    """
    Save a cropped glyph image.
    Returns the saved path.
    """
    # 用 unicode codepoint 做文件夹名，避免特殊字符问题
    safe_name = f"U{ord(character):04X}" if character and character != "?" else "unknown"
    dest_dir = GLYPH_DIR / copybook_id / safe_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    uid = uuid.uuid4().hex[:8]
    filename = f"{uid}.png"
    dest = dest_dir / filename

    # Glyphs saved as PNG to preserve ink quality
    cv2.imwrite(str(dest), crop)
    return dest


def public_url(path: Path) -> str:
    """Convert local path to a URL the frontend can fetch."""
    # Strip leading path up to 'uploads/'
    parts = path.parts
    try:
        idx = parts.index("uploads")
        return "/" + "/".join(parts[idx:])
    except ValueError:
        return str(path)
