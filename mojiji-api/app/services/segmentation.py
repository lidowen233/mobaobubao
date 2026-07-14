"""
Glyph segmentation using GPT-4o Vision.
Simple and direct: send image, get back per-character bbox + content.
"""

import os
import base64
import json
import httpx
import cv2
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DetectedGlyph:
    px: int; py: int; pw: int; ph: int
    x: float; y: float; w: float; h: float
    confidence: float
    character: str = "?"


def _encode_image(image_path: Path, max_size: int = 1500) -> tuple[str, str]:
    img = cv2.imread(str(image_path))
    h, w = img.shape[:2]
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode("utf-8"), "image/jpeg"

PROMPT = """请分析这张书法图片，识别每个汉字的位置。

图片是竖排书法，从右到左阅读。请按列从右到左，每列从上到下的顺序返回所有汉字。

请忽略边框、印章和说明文字，只返回书法正文中的汉字。

返回 JSON 数组，坐标为相对图片的比例值（0到1）：
[{"char":"大","x":0.83,"y":0.02,"w":0.12,"h":0.10}]

w 和 h 请根据每个字的实际大小填写。只返回 JSON，不要其他文字。
注意：请确保识别图片中所有列的所有汉字，不要遗漏最左边的列。"""


def segment_page(image_path: Path) -> list[DetectedGlyph]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    img_orig = cv2.imread(str(image_path))
    if img_orig is None:
        raise ValueError(f"Cannot read image: {image_path}")
    h, w = img_orig.shape[:2]

    b64, media_type = _encode_image(image_path)

    payload = {
        "model": "gpt-4o",
        "max_tokens": 8192,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:{media_type};base64,{b64}",
                    "detail": "high"
                }},
                {"type": "text", "text": PROMPT}
            ]
        }]
    }

    for attempt in range(3):
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"].strip()
        finish_reason = resp.json()["choices"][0].get("finish_reason", "")
        print(f"[GPT attempt {attempt+1}] finish_reason={finish_reason}, length={len(content)}")

        if finish_reason == "stop" and content:
            break
        print(f"[GPT] incomplete response, retrying...")

    print(f"[GPT raw]: {content}")
    # Strip markdown fences if present
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    raw = json.loads(content)
    print(f"[segmentation] GPT returned {len(raw)} glyphs")

    glyphs = []
    for item in raw:
        gx = float(item["x"]); gy = float(item["y"])
        gw = float(item["w"]); gh = float(item["h"])
        char = str(item.get("char", "?"))

        if gw <= 0 or gh <= 0:
            continue

        # Clamp to image bounds
        gx = max(0.0, min(gx, 1.0))
        gy = max(0.0, min(gy, 1.0))
        gw = min(gw, 1.0 - gx)
        gh = min(gh, 1.0 - gy)

        glyphs.append(DetectedGlyph(
            px=int(gx * w), py=int(gy * h),
            pw=int(gw * w), ph=int(gh * h),
            x=gx, y=gy, w=gw, h=gh,
            confidence=0.9,
            character=char,
        ))

    return glyphs


def sort_glyphs_rtl(glyphs: list[DetectedGlyph], col_tolerance: float = 0.06) -> list[DetectedGlyph]:
    if not glyphs:
        return glyphs
    def col_index(g: DetectedGlyph) -> int:
        cx = g.x + g.w / 2
        return int((1.0 - cx) / col_tolerance)
    return sorted(glyphs, key=lambda g: (col_index(g), g.y))


def crop_glyph(image_path: Path, glyph: DetectedGlyph, padding: float = 0.08) -> np.ndarray:
    img = cv2.imread(str(image_path))
    ih, iw = img.shape[:2]

    pad_x = int(glyph.pw * padding)
    pad_y = int(glyph.ph * padding)
    x1 = max(0, glyph.px - pad_x)
    y1 = max(0, glyph.py - pad_y)
    x2 = min(iw, glyph.px + glyph.pw + pad_x)
    y2 = min(ih, glyph.py + glyph.ph + pad_y)

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return np.zeros((10, 10, 3), dtype=np.uint8)
    return crop
