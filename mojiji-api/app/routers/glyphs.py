from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from prisma import Prisma

router = APIRouter(prefix="/glyphs", tags=["glyphs"])
db = Prisma()


class GlyphLabel(BaseModel):
    character: str
    verified: bool = True


class GlyphOut(BaseModel):
    id: str
    character: str
    imageUrl: str
    confidence: float | None
    verified: bool
    copybookTitle: str | None = None
    calligrapher: str | None = None
    pageNumber: int | None = None


@router.get("", response_model=list[GlyphOut])
async def search_glyphs(
    character: str = Query(..., description="单个汉字，如 '月'"),
    verified_only: bool = Query(False),
    limit: int = Query(20, le=100),
):
    """Search all glyph variants for a given character."""
    where: dict = {"character": character}
    if verified_only:
        where["verified"] = True

    glyphs = await db.glyph.find_many(
        where=where,
        take=limit,
        include={"page": {"include": {"copybook": True}}},
    )

    results = []
    for g in glyphs:
        page = g.page
        cb   = page.copybook if page else None
        results.append(GlyphOut(
            id=g.id,
            character=g.character,
            imageUrl=g.imageUrl,
            confidence=g.confidence,
            verified=g.verified,
            copybookTitle=cb.title if cb else None,
            calligrapher=cb.calligrapher if cb else None,
            pageNumber=page.pageNumber if page else None,
        ))
    return results


@router.patch("/{glyph_id}/label")
async def label_glyph(glyph_id: str, body: GlyphLabel):
    """Manually assign a character to a detected glyph (post-OCR correction)."""
    glyph = await db.glyph.find_unique(where={"id": glyph_id})
    if not glyph:
        raise HTTPException(404, "Glyph not found")

    updated = await db.glyph.update(
        where={"id": glyph_id},
        data={"character": body.character, "verified": body.verified},
    )
    return updated


@router.delete("/{glyph_id}", status_code=204)
async def delete_glyph(glyph_id: str):
    """Remove a false-positive glyph detection."""
    await db.glyph.delete(where={"id": glyph_id})


@router.get("/unverified", response_model=list[GlyphOut])
async def unverified_glyphs(limit: int = Query(50, le=200)):
    """Return glyphs pending human review (character == '?' or verified == False)."""
    glyphs = await db.glyph.find_many(
        where={"OR": [{"verified": False}, {"character": "?"}]},
        take=limit,
        include={"page": {"include": {"copybook": True}}},
        order={"confidence": "desc"},
    )
    results = []
    for g in glyphs:
        page = g.page
        cb   = page.copybook if page else None
        results.append(GlyphOut(
            id=g.id, character=g.character, imageUrl=g.imageUrl,
            confidence=g.confidence, verified=g.verified,
            copybookTitle=cb.title if cb else None,
            calligrapher=cb.calligrapher if cb else None,
            pageNumber=page.pageNumber if page else None,
        ))
    return results
