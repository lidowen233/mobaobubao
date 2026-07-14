from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
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
        id=cb.id, title=cb.title, calligrapher=cb.calligrapher,
        dynasty=cb.dynasty, script=cb.script, source=cb.source,
    )


@router.get("", response_model=list[CopybookOut])
async def list_copybooks():
    cbs = await db.copybook.find_many(include={"pages": True})
    return [
        CopybookOut(
            id=cb.id, title=cb.title, calligrapher=cb.calligrapher,
            dynasty=cb.dynasty, script=cb.script, source=cb.source,
            pageCount=len(cb.pages) if cb.pages else 0,
        )
        for cb in cbs
    ]


@router.get("/{copybook_id}")
async def get_copybook(copybook_id: str):
    cb = await db.copybook.find_unique(
        where={"id": copybook_id},
        include={"pages": True},
    )
    if not cb:
        raise HTTPException(404, "Copybook not found")
    return cb


@router.post("/{copybook_id}/pages", status_code=201)
async def upload_page(
    copybook_id: str,
    background_tasks: BackgroundTasks,
    page_number: int = Form(...),
    file: UploadFile = File(...),
):
    cb = await db.copybook.find_unique(where={"id": copybook_id})
    if not cb:
        raise HTTPException(404, "Copybook not found")

    existing = await db.copybookpage.find_unique(
        where={"copybookId_pageNumber": {"copybookId": copybook_id, "pageNumber": page_number}}
    )
    if existing:
        raise HTTPException(409, f"Page {page_number} already exists")

    try:
        saved_path, w, h = await save_page_image(file, copybook_id, page_number)
    except StorageError as e:
        raise HTTPException(422, str(e))

    page = await db.copybookpage.create(data={
        "copybookId": copybook_id,
        "pageNumber": page_number,
        "imageUrl":   public_url(saved_path),
        "width":      w,
        "height":     h,
        "processed":  False,
    })

    background_tasks.add_task(_run_segmentation, page.id, saved_path)

    return {
        "pageId":     page.id,
        "pageNumber": page_number,
        "width":      w,
        "height":     h,
        "imageUrl":   page.imageUrl,
        "status":     "processing",
    }


@router.get("/{copybook_id}/pages")
async def list_pages(copybook_id: str):
    pages = await db.copybookpage.find_many(
        where={"copybookId": copybook_id},
        order={"pageNumber": "asc"},
    )
    return pages


@router.get("/{copybook_id}/pages/{page_id}/glyphs")
async def list_page_glyphs(copybook_id: str, page_id: str):
    glyphs = await db.glyph.find_many(
        where={"pageId": page_id},
        order={"bboxY": "asc"},
    )
    return glyphs


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
    print(f"[segmentation] page {page_id}: {created} glyphs detected")
