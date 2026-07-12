export interface ScannedGlyph {
  id: string
  imageUrl: string   // cropped glyph image from backend
  bboxX: number      // normalised 0-1
  bboxY: number
  bboxW: number
  bboxH: number
  confidence: number
  pageId: string
}

export interface ScannedPage {
  id: string
  pageNumber: number
  imageUrl: string
  width: number
  height: number
  glyphs: ScannedGlyph[]
}

export interface UploadedCopybook {
  id: string
  title: string
  calligrapher: string
  script: string
}
