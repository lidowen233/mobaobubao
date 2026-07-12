import type { GridType, PaperType } from '@/types'
import type { PaperSize } from '@/store/compositionStore'

export function buildGridPath(type: GridType, size: number): string {
  if (type === 'none') return ''
  const h = size / 2
  const t = size / 3
  const t2 = (size * 2) / 3
  if (type === 'mi') return `M${h},0 L${h},${size} M0,${h} L${size},${h}`
  if (type === 'jiu') return `M${t},0 L${t},${size} M${t2},0 L${t2},${size} M0,${t} L${size},${t} M0,${t2} L${size},${t2}`
  return ''
}

export function buildDiagPath(size: number): string {
  return `M0,0 L${size},${size} M${size},0 L0,${size}`
}

export const PAPER_COLORS: Record<PaperType, string> = {
  xuan: '#faf5ec',
  red:  '#fdf0e8',
  dark: '#1a120a',
}

export const PAPER_INK: Record<PaperType, string> = {
  xuan: '#120a02',
  red:  '#120a02',
  dark: '#e8dcc8',
}

export const PAPER_BORDER: Record<PaperType, string> = {
  xuan: '#c4b9ae',
  red:  '#d4a898',
  dark: '#3a2a1a',   // near-invisible on dark — same family as bg
}

// Grid line color per paper type
export const GRID_COLOR: Record<PaperType, string> = {
  xuan: '#9b2335',
  red:  '#9b2335',
  dark: '#c8a84b',   // gold on black
}

// Paper physical dimensions in mm → we'll use aspect ratio for display
export const PAPER_SIZES: Record<PaperSize, { label: string; w: number; h: number }> = {
  a4:        { label: 'A4',   w: 210, h: 297 },
  liuchi:    { label: '六尺', w: 180, h: 97  },   // 六尺整张横幅 (180×97cm) — landscape
  sichi:     { label: '四尺', w: 138, h: 69  },   // landscape
  fangzhang: { label: '丈二', w: 144, h: 367 },   // tall scroll
}
