"""
Glyph segmentation using an OpenAI vision model.

The model detects the bounding box and character of each main-text
calligraphy glyph. Results are validated and sorted in traditional
Chinese reading order:

    right-to-left columns
    top-to-bottom within each column
"""

from __future__ import annotations

import os
import base64
import json
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import httpx


# ============================================================
# Data model
# ============================================================

@dataclass
class DetectedGlyph:
    # Pixel coordinates in the original image
    px: int
    py: int
    pw: int
    ph: int

    # Normalized coordinates relative to original image
    x: float
    y: float
    w: float
    h: float

    character: str = "?"

    # Model-reported confidence is not a calibrated probability.
    # Keep it optional instead of assigning a fake constant such as 0.9.
    confidence: float | None = None


# ============================================================
# Image helpers
# ============================================================

def _encode_image(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def _get_media_type(image_path: Path) -> str:
    suffix = image_path.suffix.lower()

    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }

    if suffix not in media_types:
        raise ValueError(f"Unsupported image format: {suffix}")

    return media_types[suffix]


def _get_image_size(image_path: Path) -> tuple[int, int]:
    """
    Return image size as (width, height).
    """
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    height, width = img.shape[:2]
    return width, height


# ============================================================
# Prompt
# ============================================================

SYSTEM_PROMPT = """
你是一个专业的中国书法字帖字形检测助手。

你的任务是识别图片中“正文区域”的每一个独立汉字，并返回每个字的：
1. 字符内容；
2. 紧贴该字墨迹主体的边界框。

识别规则：

- 只识别书法作品正文中的汉字。
- 忽略装饰边框、底纹、题签、印章、落款、作者名、编辑信息、
  出版信息、水印和页面标题。
- 一个边界框只能对应一个汉字。
- 不要把整列文字合并成一个框。
- 不要把两个相邻汉字放进同一个框。
- 边界框应覆盖完整字形，但不要包含大量空白或相邻文字。
- 残缺但可判断的正文汉字仍应返回。
- 无法可靠辨认的正文汉字，将 character 返回为 "?"。
- 不要因为印章遮挡而把印章识别成正文。
- 不要根据你熟悉的古文内容补写图片中实际不存在的字。
- 必须根据图片中可见的字形逐字检测。

坐标规则：

- x、y、w、h 均为相对于整张原图的比例坐标，范围为 0 到 1。
- x、y 是边界框左上角。
- w、h 是边界框宽度和高度。
- 坐标必须基于整张输入图片，包括边框区域，而不是裁剪后的正文区域。

输出要求：

- 返回所有检测到的正文汉字。
- 模型不需要负责最终阅读顺序，后端会再次排序。
- 只按照指定 JSON Schema 返回结果。
""".strip()


# ============================================================
# Structured output schema
# ============================================================

GLYPH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "glyphs": {
            "type": "array",
            "description": "图片正文区域内检测到的所有独立书法汉字。",
            "items": {
                "type": "object",
                "properties": {
                    "character": {
                        "type": "string",
                        "description": "单个汉字；无法辨认时为 ?。",
                    },
                    "x": {
                        "type": "number",
                        "description": "相对于整张图片宽度的左上角 x 坐标，0 到 1。",
                    },
                    "y": {
                        "type": "number",
                        "description": "相对于整张图片高度的左上角 y 坐标，0 到 1。",
                    },
                    "w": {
                        "type": "number",
                        "description": "相对于整张图片宽度的边界框宽度，0 到 1。",
                    },
                    "h": {
                        "type": "number",
                        "description": "相对于整张图片高度的边界框高度，0 到 1。",
                    },
                },
                "required": ["character", "x", "y", "w", "h"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["glyphs"],
    "additionalProperties": False,
}


# ============================================================
# Validation helpers
# ============================================================

def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clean_character(value: Any) -> str:
    """
    Normalize model output to one visible character.

    Keeps '?' for uncertain glyphs. If the model accidentally returns
    surrounding whitespace or multiple characters, preserve only the
    first non-whitespace character.
    """
    text = str(value or "").strip()

    if not text:
        return "?"

    if text == "?":
        return "?"

    return text[0]


def _is_valid_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False

    return math.isfinite(number)


def _intersection_over_union(
    a: DetectedGlyph,
    b: DetectedGlyph,
) -> float:
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h

    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)

    area_a = a.w * a.h
    area_b = b.w * b.h
    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def _remove_duplicate_boxes(
    glyphs: list[DetectedGlyph],
    iou_threshold: float = 0.65,
) -> list[DetectedGlyph]:
    """
    Remove obvious duplicate detections.

    If two boxes overlap heavily, prefer:
    1. a recognized character over '?';
    2. otherwise the smaller/tighter box.
    """
    kept: list[DetectedGlyph] = []

    candidates = sorted(
        glyphs,
        key=lambda g: (
            g.character == "?",
            g.w * g.h,
        ),
    )

    for candidate in candidates:
        duplicate = any(
            _intersection_over_union(candidate, existing) >= iou_threshold
            for existing in kept
        )

        if not duplicate:
            kept.append(candidate)

    return kept


# ============================================================
# RTL column sorting
# ============================================================

def sort_glyphs_rtl(
    glyphs: list[DetectedGlyph],
    column_tolerance: float | None = None,
) -> list[DetectedGlyph]:
    """
    Sort glyphs by traditional vertical Chinese reading order:

        columns: right -> left
        within each column: top -> bottom

    Nearby x-center coordinates are grouped into the same column.
    """
    if not glyphs:
        return []

    widths = sorted(g.w for g in glyphs)
    median_width = widths[len(widths) // 2]

    if column_tolerance is None:
        # A little over half the median glyph width generally works for
        # vertical copybook columns.
        column_tolerance = max(0.012, median_width * 0.65)

    # Start from rightmost glyphs.
    candidates = sorted(
        glyphs,
        key=lambda g: (-(g.x + g.w / 2), g.y),
    )

    columns: list[list[DetectedGlyph]] = []
    column_centers: list[float] = []

    for glyph in candidates:
        center_x = glyph.x + glyph.w / 2

        best_index: int | None = None
        best_distance = float("inf")

        for index, existing_center in enumerate(column_centers):
            distance = abs(center_x - existing_center)

            if distance <= column_tolerance and distance < best_distance:
                best_index = index
                best_distance = distance

        if best_index is None:
            columns.append([glyph])
            column_centers.append(center_x)
        else:
            columns[best_index].append(glyph)

            # Update running column center.
            column_centers[best_index] = sum(
                item.x + item.w / 2
                for item in columns[best_index]
            ) / len(columns[best_index])

    # Columns right -> left.
    paired_columns = sorted(
        zip(column_centers, columns),
        key=lambda pair: -pair[0],
    )

    ordered: list[DetectedGlyph] = []

    for _, column in paired_columns:
        # Each column top -> bottom.
        ordered.extend(
            sorted(
                column,
                key=lambda g: (
                    g.y + g.h / 2,
                    -(g.x + g.w / 2),
                ),
            )
        )

    return ordered


# ============================================================
# API response extraction
# ============================================================

def _extract_response_text(response_json: dict[str, Any]) -> str:
    """
    Extract output_text from a raw Responses API response.
    """
    for output_item in response_json.get("output", []):
        if output_item.get("type") != "message":
            continue

        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                text = content_item.get("text")

                if isinstance(text, str):
                    return text

    raise ValueError(
        "The API response did not contain an output_text item."
    )


# ============================================================
# Main segmentation function
# ============================================================

def segment_page(
    image_path: Path,
    *,
    model: str | None = None,
    timeout: float = 120.0,
) -> list[DetectedGlyph]:
    """
    Send a copybook page to an OpenAI vision model and return glyphs.

    Environment variables:
        OPENAI_API_KEY
        OPENAI_VISION_MODEL, optional

    A model supporting image inputs and Structured Outputs is required.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(image_path)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set in the environment."
        )

    model = (
        model
        or os.getenv("OPENAI_VISION_MODEL")
        or "gpt-5.6"
    )

    image_width, image_height = _get_image_size(image_path)

    b64 = _encode_image(image_path)
    media_type = _get_media_type(image_path)
    data_url = f"data:{media_type};base64,{b64}"

    payload = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "检测这张书法字帖正文中的每一个独立汉字。"
                            "不要识别右侧题签、印章、边框和编辑信息。"
                            "边界框必须使用相对于整张原图的坐标。"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        # Dense calligraphy pages are spatially sensitive.
                        # gpt-5.4+ models support "original".
                        "detail": "original",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "calligraphy_glyph_detection",
                "strict": True,
                "schema": GLYPH_SCHEMA,
            }
        },
        "max_output_tokens": 12000,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.is_error:
                raise RuntimeError(
                    "OpenAI API request failed "
                    f"({response.status_code}): {response.text}"
                )

    except httpx.TimeoutException as exc:
        raise TimeoutError(
            f"OpenAI request exceeded {timeout} seconds."
        ) from exc

    response_json = response.json()
    content = _extract_response_text(response_json)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Model returned invalid JSON: {content[:500]}"
        ) from exc

    raw_glyphs = parsed.get("glyphs")

    if not isinstance(raw_glyphs, list):
        raise ValueError("Response field 'glyphs' is not a list.")

    glyphs: list[DetectedGlyph] = []

    for item in raw_glyphs:
        if not isinstance(item, dict):
            continue

        required_values = [
            item.get("x"),
            item.get("y"),
            item.get("w"),
            item.get("h"),
        ]

        if not all(_is_valid_number(v) for v in required_values):
            continue

        gx = float(item["x"])
        gy = float(item["y"])
        gw = float(item["w"])
        gh = float(item["h"])

        # Completely invalid boxes.
        if gw <= 0 or gh <= 0:
            continue

        # Boxes whose origin is far outside the image.
        if gx >= 1 or gy >= 1:
            continue

        # Clamp slightly inaccurate coordinates to the image boundary.
        gx = _clamp(gx, 0.0, 1.0)
        gy = _clamp(gy, 0.0, 1.0)
        gw = _clamp(gw, 0.0, 1.0 - gx)
        gh = _clamp(gh, 0.0, 1.0 - gy)

        # Reject boxes that become empty after clipping.
        if gw < 0.002 or gh < 0.002:
            continue

        # Reject implausibly huge boxes. A single calligraphy glyph should
        # not occupy most of the page.
        if gw > 0.35 or gh > 0.45:
            continue

        character = _clean_character(item.get("character"))

        px = round(gx * image_width)
        py = round(gy * image_height)
        pw = max(1, round(gw * image_width))
        ph = max(1, round(gh * image_height))

        # Ensure pixel boxes remain inside the original image.
        px = min(max(px, 0), image_width - 1)
        py = min(max(py, 0), image_height - 1)
        pw = min(pw, image_width - px)
        ph = min(ph, image_height - py)

        glyphs.append(
            DetectedGlyph(
                px=px,
                py=py,
                pw=pw,
                ph=ph,
                x=gx,
                y=gy,
                w=gw,
                h=gh,
                character=character,
                confidence=None,
            )
        )

    glyphs = _remove_duplicate_boxes(glyphs)
    glyphs = sort_glyphs_rtl(glyphs)

    return glyphs


# ============================================================
# Cropping
# ============================================================

def crop_glyph(
    image_path: Path,
    glyph: DetectedGlyph,
    padding: float = 0.08,
):
    """
    Crop a single glyph with proportional padding.

    Returns:
        BGR numpy array.
    """
    import cv2

    if padding < 0:
        raise ValueError("padding must be non-negative")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    image_height, image_width = img.shape[:2]

    pad_x = round(glyph.pw * padding)
    pad_y = round(glyph.ph * padding)

    x1 = max(0, glyph.px - pad_x)
    y1 = max(0, glyph.py - pad_y)
    x2 = min(image_width, glyph.px + glyph.pw + pad_x)
    y2 = min(image_height, glyph.py + glyph.ph + pad_y)

    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            f"Invalid crop for glyph {glyph.character!r}: "
            f"{x1}, {y1}, {x2}, {y2}"
        )

    return img[y1:y2, x1:x2].copy()


# ============================================================
# Optional debugging utilities
# ============================================================

def save_detection_preview(
    image_path: Path,
    glyphs: list[DetectedGlyph],
    output_path: Path,
) -> None:
    """
    Draw bounding boxes and reading-order indices for inspection.

    Chinese characters may not render correctly with cv2.putText,
    so the preview uses numeric indices.
    """
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    for index, glyph in enumerate(glyphs, start=1):
        x1 = glyph.px
        y1 = glyph.py
        x2 = glyph.px + glyph.pw
        y2 = glyph.py + glyph.ph

        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            img,
            str(index),
            (x1, max(15, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(output_path), img):
        raise IOError(f"Failed to save preview: {output_path}")


def save_glyph_crops(
    image_path: Path,
    glyphs: list[DetectedGlyph],
    output_dir: Path,
    padding: float = 0.08,
) -> None:
    """
    Save every glyph crop in detected reading order.
    """
    import cv2

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, glyph in enumerate(glyphs, start=1):
        crop = crop_glyph(image_path, glyph, padding=padding)

        safe_character = (
            glyph.character
            if glyph.character not in {"?", "/", "\\", ":"}
            else "unknown"
        )

        output_path = output_dir / (
            f"{index:03d}_{safe_character}.png"
        )

        if not cv2.imwrite(str(output_path), crop):
            raise IOError(f"Failed to save crop: {output_path}")
