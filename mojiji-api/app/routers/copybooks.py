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


from app.services.storage import save_page_image, save_glyph_crop, public_url, StorageError
from app.services.segmentation import segment_page, crop_glyph, sort_glyphs_rtl


router = APIRouter(prefix="/copybooks", tags=["copybooks"])
db = Prisma()



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


@router.post("", response_model=CopybookOut, status_code=201)
async def create_copybook(body: CopybookCreate):
    cb = await db.copybook.create(data={
        "title":        body.title,
        "calligrapher": body.calligrapher,
        "dynasty":      body.dynasty,
        "script":       body.script,
        "description":  body.description,
        "source":       "USER",
    })

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

        include={"pages": True},

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

    cb = await db.copybook.find_unique(where={"id": copybook_id})
    if not cb:
        raise HTTPException(404, "Copybook not found")

    existing = await db.copybookpage.find_unique(
        where={"copybookId_pageNumber": {"copybookId": copybook_id, "pageNumber": page_number}}

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


    background_tasks.add_task(_run_segmentation, page.id, saved_path)


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



async def _run_segmentation(page_id: str, image_path):
    from pathlib import Path
    image_path = Path(image_path)

    try:
        detected = segment_page(image_path)
        #detected = sort_glyphs_rtl(detected)
    except Exception as e:
        print(f"[segmentation] ERROR page {page_id}: {e}")
        return

    page = await db.copybookpage.find_unique(where={"id": page_id})
    if not page:
        return

    cb = await db.copybook.find_unique(where={"id": page.copybookId})
    if not cb:
        return

    created = 0
    for g in detected:
       
        safe_name = f"U{ord(g.character):04X}" if g.character and g.character != "?" else "unknown"
        
        crop = crop_glyph(image_path, g, padding=0.08)
        if crop is None or crop.size == 0 or crop.shape[0] < 5 or crop.shape[1] < 5:
            continue
        crop_path = save_glyph_crop(crop, cb.id, character=safe_name)

        await db.glyph.create(data={
            "character":  g.character,
            "pageId":     page_id,
            "imageUrl":   public_url(crop_path),
            "bboxX":      g.x,
            "bboxY":      g.y,
            "bboxW":      g.w,
            "bboxH":      g.h,
            "confidence": g.confidence,
            "verified":   False,
        })
        created += 1

    await db.copybookpage.update(
        where={"id": page_id},
        data={"processed": True},

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
