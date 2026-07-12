// ── Glyph / copybook data ────────────────────────────────────────────────────

export type Script = 'kai' | 'xing' | 'cao' | 'li' | 'zhuan'

export interface Copybook {
  id: string
  title: string         // e.g. "兰亭序"
  calligrapher: string  // e.g. "王羲之"
  dynasty: string       // e.g. "东晋"
  script: Script
  source: 'system' | 'user'
  coverUrl?: string
}

export interface Glyph {
  id: string
  character: string     // single Han character
  copybookId: string
  imageUrl: string      // cropped glyph image
  bbox?: BBox           // position in original scan
  uploaderId?: string   // null = system
}

// Bounding box in original copybook scan (normalised 0–1)
export interface BBox {
  x: number; y: number; w: number; h: number
}

// ── Composition ──────────────────────────────────────────────────────────────

export type PaperType = 'xuan' | 'red' | 'dark'
export type GridType  = 'mi' | 'jiu' | 'none'
export type Layout    = { rows: number }   // columns derived from text length

export interface GlyphSelection {
  character: string
  glyphId: string | null   // null = placeholder (char not in library yet)
}

export interface Composition {
  id: string
  text: string
  selections: GlyphSelection[]
  paper: PaperType
  grid: GridType
  layout: Layout
  createdAt: string
}

// ── UI state ─────────────────────────────────────────────────────────────────

export interface ActiveCell {
  charIndex: number
  character: string
}
