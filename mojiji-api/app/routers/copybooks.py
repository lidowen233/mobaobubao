from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel
from prisma import Prisma

from app.config import UPLOAD_DIR
from app.services.segmentation import (
    DetectedGlyph,
    crop_glyph,
    detect_glyph_boxes_yolo,
    filter_glyph_boxes,
    recognize_glyph_batch,
    sort_glyphs_rtl,
)
from app.services.storage import (
    StorageError,
    public_url,
    save_glyph_crop,
    save_page_image,
)


router = APIRouter(prefix="/copybooks", tags=["copybooks"])
db = Prisma()


# ============================================================
# Configuration
# ============================================================

YOLO_MODEL_PATH = Path(
    os.getenv(
        "CALLIGRAPHY_YOLO_MODEL",
        "runs/detect/calligraphy_glyph/weights/best.pt",
    )
)

VISION_MODEL = os.getenv(
    "CALLIGRAPHY_VISION_MODEL",
    "gpt-4o",
)


# ============================================================
# Schemas
# ============================================================

class CopybookCreate(BaseModel):
    title: str
    calligrapher: str
    dynasty: str | None = None
    script: str = "KAI"
    description: str | None = None


class CopybookOut(BaseModel):
    id: str
    title: str
    calligrapher: str
    dynasty: str | None
    script: str
    source: str
    pageCount: int = 0


# ============================================================
# Routes
# ============================================================

@router.post("", response_model=CopybookOut, status_code=201)
async def create_copybook(body: CopybookCreate):
    """Create a new copybook without pages."""
    copybook = await db.copybook.create(
        data={
            "title": body.title,
            "calligrapher": body.calligrapher,
            "dynasty": body.dynasty,
            "script": body.script,
            "description": body.description,
            "source": "USER",
        }
    )

    return CopybookOut(
        id=copybook.id,
        title=copybook.title,
        calligrapher=copybook.calligrapher,
        dynasty=copybook.dynasty,
        script=copybook.script,
        source=copybook.source,
    )


@router.get("", response_model=list[CopybookOut])
async def list_copybooks():
    """Return all copybooks and their page counts."""
    copybooks = await db.copybook.find_many(
        include={"pages": True}
    )

    return [
        CopybookOut(
            id=copybook.id,
            title=copybook.title,
            calligrapher=copybook.calligrapher,
            dynasty=copybook.dynasty,
            script=copybook.script,
            source=copybook.source,
            pageCount=len(copybook.pages)
            if copybook.pages
            else 0,
        )
        for copybook in copybooks
    ]


@router.get("/{copybook_id}")
async def get_copybook(copybook_id: str):
    """Return one copybook and its pages."""
    copybook = await db.copybook.find_unique(
        where={"id": copybook_id},
        include={
            "pages": {
                "include": {
                    "glyphs": False,
                }
            }
        },
    )

    if not copybook:
        raise HTTPException(
            status_code=404,
            detail="Copybook not found",
        )

    return copybook


@router.post("/{copybook_id}/pages", status_code=201)
async def upload_page(
    copybook_id: str,
    background_tasks: BackgroundTasks,
    page_number: int = Form(...),
    file: UploadFile = File(...),

    # Optional normalized page ROI.
    # Leave these fields empty to process the entire image.
    roi_left: float | None = Form(None),
    roi_top: float | None = Form(None),
    roi_right: float | None = Form(None),
    roi_bottom: float | None = Form(None),
):
    """
    Upload one copybook page and start YOLO detection.

    ROI values use normalized coordinates from 0 to 1.
    """
    copybook = await db.copybook.find_unique(
        where={"id": copybook_id}
    )

    if not copybook:
        raise HTTPException(
            status_code=404,
            detail="Copybook not found",
        )

    existing = await db.copybookpage.find_unique(
        where={
            "copybookId_pageNumber": {
                "copybookId": copybook_id,
                "pageNumber": page_number,
            }
        }
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Page {page_number} already exists",
        )

    roi_values = (
        roi_left,
        roi_top,
        roi_right,
        roi_bottom,
    )

    supplied_roi_values = [
        value
        for value in roi_values
        if value is not None
    ]

    if supplied_roi_values and len(supplied_roi_values) != 4:
        raise HTTPException(
            status_code=422,
            detail=(
                "All four ROI values must be supplied together: "
                "roi_left, roi_top, roi_right, roi_bottom"
            ),
        )

    roi: tuple[float, float, float, float] | None = None

    if len(supplied_roi_values) == 4:
        assert roi_left is not None
        assert roi_top is not None
        assert roi_right is not None
        assert roi_bottom is not None

        if not (
            0 <= roi_left < roi_right <= 1
            and 0 <= roi_top < roi_bottom <= 1
        ):
            raise HTTPException(
                status_code=422,
                detail="ROI values must define a valid box from 0 to 1",
            )

        roi = (
            roi_left,
            roi_top,
            roi_right,
            roi_bottom,
        )

    try:
        saved_path, width, height = await save_page_image(
            file,
            copybook_id,
            page_number,
        )
    except StorageError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    page = await db.copybookpage.create(
        data={
            "copybookId": copybook_id,
            "pageNumber": page_number,
            "imageUrl": public_url(saved_path),
            "width": width,
            "height": height,
            "processed": False,
        }
    )

    background_tasks.add_task(
        _run_detection,
        page.id,
        saved_path,
        roi,
    )

    return {
        "pageId": page.id,
        "pageNumber": page_number,
        "width": width,
        "height": height,
        "imageUrl": page.imageUrl,
        "status": "processing",
    }


@router.get("/{copybook_id}/pages")
async def list_pages(copybook_id: str):
    """Return all pages in numerical order."""
    copybook = await db.copybook.find_unique(
        where={"id": copybook_id}
    )

    if not copybook:
        raise HTTPException(
            status_code=404,
            detail="Copybook not found",
        )

    return await db.copybookpage.find_many(
        where={"copybookId": copybook_id},
        order={"pageNumber": "asc"},
    )


@router.get("/{copybook_id}/pages/{page_id}/glyphs")
async def list_page_glyphs(
    copybook_id: str,
    page_id: str,
):
    """
    Return glyphs in permanent traditional reading order.

    This requires an orderIndex field in the Glyph Prisma model.
    """
    page = await db.copybookpage.find_first(
        where={
            "id": page_id,
            "copybookId": copybook_id,
        }
    )

    if not page:
        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    return await db.glyph.find_many(
        where={"pageId": page_id},
        order={"orderIndex": "asc"},
    )


@router.get("/{copybook_id}/pages/{page_id}")
async def get_page(copybook_id: str, page_id: str):
    """Return page state so clients can wait for all boxes to be persisted."""
    page = await db.copybookpage.find_first(
        where={
            "id": page_id,
            "copybookId": copybook_id,
        }
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.post("/{copybook_id}/pages/{page_id}/recognize")
async def recognize_page(
    copybook_id: str,
    page_id: str,
):
    """Recognize the page using its current, user-confirmed database boxes."""
    page = await db.copybookpage.find_first(
        where={
            "id": page_id,
            "copybookId": copybook_id,
        }
    )

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if not page.processed:
        raise HTTPException(
            status_code=409,
            detail="Glyph detection is still processing",
        )

    stored_glyphs = await db.glyph.find_many(
        where={"pageId": page_id},
        order={"orderIndex": "asc"},
    )
    if not stored_glyphs:
        raise HTTPException(
            status_code=409,
            detail="No confirmed glyph boxes are available",
        )

    try:
        image_path = _local_upload_path(page.imageUrl)
        detected = [
            _detected_glyph_from_record(glyph, page.width, page.height)
            for glyph in stored_glyphs
        ]

        # Recognition is deliberately separate from detection. These batches
        # use the permanent database order and never call YOLO or re-sort boxes.
        for start in range(0, len(detected), 12):
            await asyncio.to_thread(
                recognize_glyph_batch,
                image_path,
                detected[start:start + 12],
                model=VISION_MODEL,
            )

        for record, result in zip(stored_glyphs, detected, strict=True):
            await db.glyph.update(
                where={"id": record.id},
                data={
                    "character": result.character or "?",
                    "verified": False,
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"[recognition] ERROR page {page_id}: "
            f"{type(exc).__name__}: {exc}"
        )
        raise HTTPException(
            status_code=500,
            detail="Glyph recognition failed",
        ) from exc

    glyphs = await db.glyph.find_many(
        where={"pageId": page_id},
        order={"orderIndex": "asc"},
    )
    return {"status": "completed", "glyphs": glyphs}


def _local_upload_path(image_url: str) -> Path:
    """Map public_url() output back into the configured local upload root."""
    relative = Path(image_url.lstrip("/"))
    if not relative.parts or relative.parts[0] != UPLOAD_DIR.name:
        raise ValueError(f"Unsupported local image URL: {image_url}")

    path = (UPLOAD_DIR.parent / relative).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path != upload_root and upload_root not in path.parents:
        raise ValueError(f"Image URL escapes upload directory: {image_url}")
    if not path.is_file():
        raise FileNotFoundError(f"Page image not found: {path}")
    return path


def _detected_glyph_from_record(
    glyph,
    image_width: int,
    image_height: int,
) -> DetectedGlyph:
    """Rebuild the recognition input without detecting or changing order."""
    px = round(glyph.bboxX * image_width)
    py = round(glyph.bboxY * image_height)
    pw = max(1, round(glyph.bboxW * image_width))
    ph = max(1, round(glyph.bboxH * image_height))
    return DetectedGlyph(
        px=px,
        py=py,
        pw=pw,
        ph=ph,
        x=glyph.bboxX,
        y=glyph.bboxY,
        w=glyph.bboxW,
        h=glyph.bboxH,
        character=glyph.character or "?",
        order_id=glyph.orderIndex,
        column_id=glyph.columnIndex,
        confidence=glyph.confidence,
    )


# ============================================================
# Background detection
# ============================================================

async def _run_detection(
    page_id: str,
    image_path: str | Path,
    roi: tuple[float, float, float, float] | None = None,
) -> None:
    """
    Detect, filter, sort, crop, and store glyphs without recognition.

    YOLO processing runs in a worker thread because model inference is
    synchronous and CPU/GPU intensive.
    """
    image_path = Path(image_path)

    try:
        detected = await asyncio.to_thread(
            detect_glyph_boxes_yolo,
            image_path,
            YOLO_MODEL_PATH,
        )
        detected = filter_glyph_boxes(detected, roi=roi)
        detected = sort_glyphs_rtl(detected)
    except Exception as exc:
        print(
            f"[detection] ERROR page {page_id}: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    page = await db.copybookpage.find_unique(
        where={"id": page_id}
    )

    if not page:
        print(
            f"[detection] Page no longer exists: {page_id}"
        )
        return

    copybook = await db.copybook.find_unique(
        where={"id": page.copybookId}
    )

    if not copybook:
        print(
            "[detection] Copybook no longer exists: "
            f"{page.copybookId}"
        )
        return

    try:
        # Remove old records if the task is rerun.
        await db.glyph.delete_many(
            where={"pageId": page_id}
        )

        created = 0

        for glyph in detected:
            crop = crop_glyph(
                image_path,
                glyph,
            )

            character = "?"

            crop_path = save_glyph_crop(
                crop,
                copybook.id,
                character=character,
            )

            await db.glyph.create(
                data={
                    "character": character,
                    "pageId": page_id,
                    "imageUrl": public_url(crop_path),

                    # Normalized bounding box.
                    "bboxX": glyph.x,
                    "bboxY": glyph.y,
                    "bboxW": glyph.w,
                    "bboxH": glyph.h,

                    # Permanent reading-order metadata.
                    "orderIndex": glyph.order_id,
                    "columnIndex": glyph.column_id,

                    # Detection confidence comes from YOLO.
                    "confidence": glyph.confidence,

                    # AI-recognized glyphs still require human review.
                    "verified": False,
                }
            )

            created += 1

        await db.copybookpage.update(
            where={"id": page_id},
            data={"processed": True},
        )

        print(
            f"[detection] page {page_id}: "
            f"{created} glyph boxes ready for review"
        )

    except Exception as exc:
        print(
            f"[detection] DATABASE ERROR page {page_id}: "
            f"{type(exc).__name__}: {exc}"
        )

        # Keep processed=False when database persistence fails.
        try:
            await db.copybookpage.update(
                where={"id": page_id},
                data={"processed": False},
            )
        except Exception:
            pass
