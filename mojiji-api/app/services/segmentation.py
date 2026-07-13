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
import io
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from functools import lru_cache
import httpx

from dotenv import load_dotenv
load_dotenv()

@lru_cache(maxsize=2)
def _load_yolo_model(model_path: str):
    """Load and cache a YOLO model."""
    from ultralytics import YOLO

    return YOLO(model_path)

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
    # Permanent reading-order index
    order_id: int = -1

    # Column index; 0 is the rightmost column
    column_id: int = -1

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

from statistics import median


def sort_glyphs_rtl(
    glyphs: list[DetectedGlyph],
    *,
    column_gap_factor: float = 0.75,
    min_column_tolerance: float = 0.012,
) -> list[DetectedGlyph]:
    """
    Sort glyphs in traditional vertical Chinese reading order:

    1. Columns from right to left.
    2. Glyphs within each column from top to bottom.

    Normalized coordinates make the method independent of image size.
    """
    if not glyphs:
        return []

    # Use box centers instead of top-left coordinates to reduce width bias.
    def center_x(g: DetectedGlyph) -> float:
        return g.x + g.w / 2

    def center_y(g: DetectedGlyph) -> float:
        return g.y + g.h / 2

    median_width = median(g.w for g in glyphs)

    # Allow moderate horizontal variation within the same column.
    column_tolerance = max(
        min_column_tolerance,
        median_width * column_gap_factor,
    )

    # Process candidates from the rightmost side first.
    pending = sorted(
        glyphs,
        key=lambda g: (-center_x(g), center_y(g)),
    )

    columns: list[list[DetectedGlyph]] = []

    for glyph in pending:
        gx = center_x(glyph)

        best_column_index: int | None = None
        best_distance = float("inf")

        for column_index, column in enumerate(columns):
            column_center = median(center_x(item) for item in column)
            distance = abs(gx - column_center)

            if (
                distance <= column_tolerance
                and distance < best_distance
            ):
                best_column_index = column_index
                best_distance = distance

        if best_column_index is None:
            columns.append([glyph])
        else:
            columns[best_column_index].append(glyph)

    # Merge nearby columns that were accidentally split during clustering.
    columns = _merge_close_columns(
        columns,
        column_tolerance=column_tolerance,
    )

    # Sort columns from right to left.
    columns.sort(
        key=lambda column: -median(center_x(g) for g in column)
    )

    ordered: list[DetectedGlyph] = []

    for column_id, column in enumerate(columns):
        # Sort each column strictly from top to bottom.
        column.sort(
            key=lambda g: (
                center_y(g),
                -center_x(g),
            )
        )

        for glyph in column:
            glyph.column_id = column_id
            glyph.order_id = len(ordered)
            ordered.append(glyph)

    return ordered


def _merge_close_columns(
    columns: list[list[DetectedGlyph]],
    *,
    column_tolerance: float,
) -> list[list[DetectedGlyph]]:
    """
    Merge adjacent columns that were split because of horizontal glyph drift.
    """
    if len(columns) <= 1:
        return columns

    def center_x(g: DetectedGlyph) -> float:
        return g.x + g.w / 2

    columns = sorted(
        columns,
        key=lambda column: -median(center_x(g) for g in column),
    )

    merged: list[list[DetectedGlyph]] = []

    for column in columns:
        current_center = median(center_x(g) for g in column)

        if not merged:
            merged.append(column)
            continue

        previous_center = median(
            center_x(g)
            for g in merged[-1]
        )

        if abs(current_center - previous_center) <= column_tolerance:
            merged[-1].extend(column)
        else:
            merged.append(column)

    return merged


# ============================================================
# YOLO detection and box filtering
# ============================================================

def detect_glyph_boxes_yolo(
    image_path: Path,
    model_path: Path,
    *,
    conf_threshold: float = 0.20,
    iou_threshold: float = 0.45,
    image_size: int = 1280,
    device: str | int | None = None,
    glyph_class_id: int = 0,
) -> list[DetectedGlyph]:
    """Detect one bounding box per glyph with a custom YOLO model."""
    import cv2
    from ultralytics import YOLO

    image_path = Path(image_path)
    model_path = Path(model_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"YOLO model not found: {model_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Cannot read image: {image_path}")

    image_height, image_width = image.shape[:2]
    #model = YOLO(str(model_path))
    model = _load_yolo_model(str(model_path.resolve()))
    
    kwargs: dict[str, Any] = {
        "source": str(image_path),
        "conf": conf_threshold,
        "iou": iou_threshold,
        "imgsz": image_size,
        "verbose": False,
    }
    if device is not None:
        kwargs["device"] = device

    results = model.predict(**kwargs)
    if not results or results[0].boxes is None:
        return []

    boxes = results[0].boxes
    xyxy_boxes = boxes.xyxy.cpu().numpy()
    confidences = boxes.conf.cpu().numpy()
    class_ids = boxes.cls.cpu().numpy().astype(int)

    glyphs: list[DetectedGlyph] = []
    for xyxy, confidence, class_id in zip(xyxy_boxes, confidences, class_ids):
        if class_id != glyph_class_id:
            continue

        x1, y1, x2, y2 = map(float, xyxy)
        x1 = max(0.0, min(x1, image_width - 1))
        y1 = max(0.0, min(y1, image_height - 1))
        x2 = max(x1 + 1.0, min(x2, image_width))
        y2 = max(y1 + 1.0, min(y2, image_height))

        px = int(round(x1))
        py = int(round(y1))
        pw = max(1, int(round(x2 - x1)))
        ph = max(1, int(round(y2 - y1)))

        glyphs.append(DetectedGlyph(
            px=px,
            py=py,
            pw=pw,
            ph=ph,
            x=px / image_width,
            y=py / image_height,
            w=pw / image_width,
            h=ph / image_height,
            confidence=float(confidence),
        ))

    return glyphs


def filter_glyph_boxes(
    glyphs: list[DetectedGlyph],
    *,
    roi: tuple[float, float, float, float] | None = None,
    min_width: float = 0.006,
    min_height: float = 0.012,
    max_width: float = 0.20,
    max_height: float = 0.30,
) -> list[DetectedGlyph]:
    """Filter implausible boxes and optionally keep only boxes inside a ROI."""
    filtered: list[DetectedGlyph] = []

    for glyph in glyphs:
        if not (min_width <= glyph.w <= max_width):
            continue
        if not (min_height <= glyph.h <= max_height):
            continue

        center_x = glyph.x + glyph.w / 2
        center_y = glyph.y + glyph.h / 2

        if roi is not None:
            left, top, right, bottom = roi
            if not (left <= center_x <= right and top <= center_y <= bottom):
                continue

        filtered.append(glyph)

    return _remove_duplicate_boxes(filtered)


RECOGNITION_PROMPT = """
你是一个专业的中国书法单字识别助手。

输入图片是一张带编号的书法单字裁剪表，每个格子上方都有永久 ID。

要求：
- 识别每个 ID 对应的主要书法汉字。
- 必须原样返回图片中的 ID，不能重新编号。
- 每个 ID 必须恰好返回一次。
- 不要改变字的顺序。
- 不要根据上下文补写看不清或不存在的字。
- 忽略石碑纹理、污损、边框和印章碎片。
- 无法可靠识别时返回 "?"。
- character 只能包含一个汉字或一个问号。

只返回严格 JSON：
{
  "items": [
    {"id": 0, "character": "大"},
    {"id": 1, "character": "唐"}
  ]
}
""".strip()


def _encode_bytes(data: bytes) -> str:
    """Encode binary data as base64 text."""
    return base64.b64encode(data).decode("utf-8")


def apply_recognition_results(
    glyphs: list[DetectedGlyph],
    parsed: dict[str, Any],
) -> None:
    """Map recognized characters back by permanent order_id values."""
    recognized: dict[int, str] = {}

    for item in parsed.get("items", []):
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        recognized[item_id] = _clean_character(item.get("character", "?"))

    for glyph in glyphs:
        glyph.character = recognized.get(glyph.order_id, "?")


def recognize_glyph_batch(
    image_path: Path,
    glyphs: list[DetectedGlyph],
    *,
    model: str = "gpt-4o",
    timeout: float = 300.0,
) -> list[DetectedGlyph]:
    """Recognize a sorted batch and preserve IDs regardless of response order."""
    if not glyphs:
        return glyphs

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in the environment.")

    sheet_bytes = create_glyph_contact_sheet(image_path, glyphs)
    expected_ids = [glyph.order_id for glyph in glyphs]

    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": RECOGNITION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "识别图中所有编号单字。"
                            f"必须返回这些永久 ID：{expected_ids}。"
                            "不要按数组位置重新编号。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{_encode_bytes(sheet_bytes)}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    }

    try:
        timeout_config = httpx.Timeout(
            connect=30.0,
            read=300.0,
            write=120.0,
            pool=30.0,
        )

        with httpx.Client(timeout=timeout_config) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise TimeoutError(
            f"Glyph recognition exceeded the request timeout: {exc}"
        ) from exc

    if response.is_error:
        raise RuntimeError(
            f"OpenAI API request failed ({response.status_code}): {response.text}"
        )

    content = response.json()["choices"][0]["message"]["content"].strip()
    parsed = json.loads(content)
    apply_recognition_results(glyphs, parsed)
    return glyphs


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
    yolo_model_path: Path,
    vision_model: str = "gpt-4o",
    yolo_conf: float = 0.20,
    yolo_iou: float = 0.45,
    yolo_image_size: int = 1280,
    recognition_batch_size: int = 24,
    device: str | int | None = None,
    roi: tuple[float, float, float, float] | None = None,
) -> list[DetectedGlyph]:

    # 1. YOLO detects bounding boxes only.
    glyphs = detect_glyph_boxes_yolo(
        image_path=image_path,
        model_path=yolo_model_path,
        conf_threshold=yolo_conf,
        iou_threshold=yolo_iou,
        image_size=yolo_image_size,
        device=device,
    )

    # 2. Remove implausible or duplicate boxes.
    glyphs = filter_glyph_boxes(glyphs, roi=roi)

    # 3. Sort boxes before recognition.
    glyphs = sort_glyphs_rtl(glyphs)

    # 4. Recognize batches after the permanent reading order is assigned.
    for start in range(
        0,
        len(glyphs),
        recognition_batch_size,
    ):
        batch = glyphs[
            start:start + recognition_batch_size
        ]

        recognize_glyph_batch(
            image_path=image_path,
            glyphs=batch,
            model=vision_model,
        )

    # Do not sort again after recognition.
    return glyphs

def create_glyph_contact_sheet(
    image_path: Path,
    glyphs: list[DetectedGlyph],
    *,
    crop_size: int = 180,
    columns: int = 5,
    padding_ratio: float = 0.12,
) -> bytes:
    from PIL import Image, ImageDraw
    import io
    import math

    source = Image.open(image_path).convert("RGB")

    rows = math.ceil(len(glyphs) / columns)

    label_height = 34
    cell_width = crop_size
    cell_height = crop_size + label_height

    sheet = Image.new(
        "RGB",
        (columns * cell_width, rows * cell_height),
        "white",
    )

    draw = ImageDraw.Draw(sheet)

    for sheet_index, glyph in enumerate(glyphs):
        pad_x = round(glyph.pw * padding_ratio)
        pad_y = round(glyph.ph * padding_ratio)

        x1 = max(0, glyph.px - pad_x)
        y1 = max(0, glyph.py - pad_y)
        x2 = min(
            source.width,
            glyph.px + glyph.pw + pad_x,
        )
        y2 = min(
            source.height,
            glyph.py + glyph.ph + pad_y,
        )

        crop = source.crop((x1, y1, x2, y2))
        crop.thumbnail(
            (crop_size - 16, crop_size - 16)
        )

        cell_x = (
            sheet_index % columns
        ) * cell_width

        cell_y = (
            sheet_index // columns
        ) * cell_height

        paste_x = (
            cell_x
            + (cell_width - crop.width) // 2
        )

        paste_y = (
            cell_y
            + label_height
            + (crop_size - crop.height) // 2
        )

        sheet.paste(crop, (paste_x, paste_y))

        # Display the permanent reading-order ID.
        draw.text(
            (cell_x + 8, cell_y + 7),
            f"ID {glyph.order_id}",
            fill="black",
        )

    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue()
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
