import { useState } from 'react'
import { buildGridPath, buildDiagPath, GRID_COLOR } from '@/lib/grid'
import { useCompositionStore } from '@/store/compositionStore'
import type { ScannedPage, ScannedGlyph } from '@/types/practice'

interface Props {
  pages: ScannedPage[]
  onBack: () => void
}

const CELL_SIZE = 80
const PREVIEW_SIZE = 200

export function PracticePage({ pages, onBack }: Props) {
  const { grid, paper } = useCompositionStore()
  const [activeGlyph, setActiveGlyph] = useState<ScannedGlyph | null>(null)
  const [activePage, setActivePage]   = useState(0)

  const currentPage = pages[activePage]
  if (!currentPage) return null

  const gridColor  = GRID_COLOR[paper]
  const solidPath  = buildGridPath(grid, PREVIEW_SIZE)
  const diagPath   = grid === 'mi' ? buildDiagPath(PREVIEW_SIZE) : ''

  // glyphs already sorted RTL by backend (bboxX desc, bboxY asc)
  const glyphs = currentPage.glyphs

  // Group into columns for RTL display (same logic as PaperGrid)
  const rows = 6
  const numCols = Math.ceil(glyphs.length / rows)
  const columns: (ScannedGlyph | null)[][] = []
  for (let c = 0; c < numCols; c++) {
    const col: (ScannedGlyph | null)[] = []
    for (let r = 0; r < rows; r++) {
      const i = c * rows + r
      col.push(i < glyphs.length ? glyphs[i] : null)
    }
    columns.push(col)
  }

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', background: '#f5f1eb' }}>

      {/* ── Left: glyph grid ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* page tabs */}
        {pages.length > 1 && (
          <div style={{ display: 'flex', gap: 6 }}>
            {pages.map((p, i) => (
              <button key={p.id} onClick={() => { setActivePage(i); setActiveGlyph(null) }}
                style={{
                  padding: '4px 12px', borderRadius: 4, fontSize: 12, cursor: 'pointer',
                  background: i === activePage ? '#120a02' : '#faf5ec',
                  color:      i === activePage ? '#faf5ec' : '#9a8a78',
                  border: '0.5px solid #c4b9ae',
                }}>
                第 {p.pageNumber} 页
              </button>
            ))}
          </div>
        )}

        {/* RTL glyph grid */}
        <div style={{ display: 'flex', flexDirection: 'row-reverse', gap: 6, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {columns.map((col, ci) => (
            <div key={ci} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {col.map((glyph, ri) => {
                if (!glyph) return (
                  <div key={ri} style={{ width: CELL_SIZE, height: CELL_SIZE, opacity: 0.15,
                    border: '1px dashed #c4b9ae', borderRadius: 4 }} />
                )
                const isActive = activeGlyph?.id === glyph.id
                return (
                  <GlyphCell
                    key={glyph.id}
                    glyph={glyph}
                    size={CELL_SIZE}
                    grid={grid}
                    gridColor={gridColor}
                    active={isActive}
                    onClick={() => setActiveGlyph(glyph)}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* ── Divider ──────────────────────────────────────────────────────── */}
      <div style={{ width: 1, background: '#d4ccc0', flexShrink: 0 }} />

      {/* ── Right: preview panel ─────────────────────────────────────────── */}
      <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column',
        background: '#f5f1eb', overflow: 'hidden' }}>

        {/* header */}
        <div style={{ padding: '10px 14px', borderBottom: '0.5px solid #d4ccc0',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: '#9a8a78' }}>
            {currentPage.glyphs.length} 个字形 · 第 {currentPage.pageNumber} 页
          </span>
          <button onClick={onBack}
            style={{ fontSize: 11, color: '#9a8a78', background: 'none', border: 'none', cursor: 'pointer' }}>
            ← 返回上传
          </button>
        </div>

        {!activeGlyph ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 8, padding: 20 }}>
            <div style={{ fontSize: 48, opacity: 0.1, fontFamily: "'Kaiti SC',serif" }}>字</div>
            <p style={{ fontSize: 12, color: '#9a8a78', textAlign: 'center', lineHeight: 1.7 }}>
              点击左边的字格<br />在此放大预览
            </p>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: 16, gap: 12, overflow: 'hidden' }}>

            {/* large preview with grid overlay */}
            <div style={{ position: 'relative', width: PREVIEW_SIZE, height: PREVIEW_SIZE,
              border: '1.5px solid #c4b9ae', borderRadius: 4, overflow: 'hidden', flexShrink: 0 }}>

              {/* actual glyph image */}
              <img
                src={activeGlyph.imageUrl}
                alt="字形"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
              />

              {/* grid overlay */}
              {grid !== 'none' && (
                <svg viewBox={`0 0 ${PREVIEW_SIZE} ${PREVIEW_SIZE}`}
                  width={PREVIEW_SIZE} height={PREVIEW_SIZE}
                  style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                  {solidPath && <path d={solidPath} stroke={gridColor} strokeWidth="1" opacity="0.4" fill="none" />}
                  {diagPath  && <path d={diagPath}  stroke={gridColor} strokeWidth="0.7" opacity="0.22" fill="none" strokeDasharray="4 3" />}
                </svg>
              )}
            </div>

            {/* nav between glyphs */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <NavBtn onClick={() => {
                const idx = glyphs.findIndex(g => g.id === activeGlyph.id)
                if (idx > 0) setActiveGlyph(glyphs[idx - 1])
              }}>‹</NavBtn>
              <span style={{ fontSize: 11, color: '#9a8a78', minWidth: 60, textAlign: 'center' }}>
                {glyphs.findIndex(g => g.id === activeGlyph.id) + 1} / {glyphs.length}
              </span>
              <NavBtn onClick={() => {
                const idx = glyphs.findIndex(g => g.id === activeGlyph.id)
                if (idx < glyphs.length - 1) setActiveGlyph(glyphs[idx + 1])
              }}>›</NavBtn>
            </div>

            {/* confidence badge */}
            <div style={{ fontSize: 10, color: '#b8ae9e' }}>
              识别置信度 {Math.round((activeGlyph.confidence ?? 0) * 100)}%
            </div>

            {/* thumbnail of original page with bbox highlight */}
            <div style={{ marginTop: 'auto', width: '100%' }}>
              <p style={{ fontSize: 10, color: '#b8ae9e', marginBottom: 6 }}>在原帖中的位置</p>
              <PageThumbnail page={pages[activePage]} activeGlyph={activeGlyph} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function GlyphCell({ glyph, size, grid, gridColor, active, onClick }: {
  glyph: ScannedGlyph; size: number; grid: string; gridColor: string; active: boolean; onClick: () => void
}) {
  const solidPath = buildGridPath(grid as 'mi' | 'jiu' | 'none', size)
  const diagPath  = grid === 'mi' ? buildDiagPath(size) : ''

  return (
    <div onClick={onClick} style={{
      width: size, height: size, position: 'relative', cursor: 'pointer',
      border: active ? '2px solid #9b2335' : '1px solid #c4b9ae',
      borderRadius: 4, overflow: 'hidden', background: '#faf5ec',
      transition: 'transform 0.1s',
    }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.transform = 'scale(1.04)' }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
    >
      <img src={glyph.imageUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      {grid !== 'none' && (
        <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}
          style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {solidPath && <path d={solidPath} stroke={gridColor} strokeWidth="0.9" opacity="0.3" fill="none" />}
          {diagPath  && <path d={diagPath}  stroke={gridColor} strokeWidth="0.6" opacity="0.18" fill="none" strokeDasharray="4 3" />}
        </svg>
      )}
    </div>
  )
}

function PageThumbnail({ page, activeGlyph }: { page: ScannedPage; activeGlyph: ScannedGlyph }) {
  const thumbW = 220
  const thumbH = Math.round((page.height / page.width) * thumbW)
  const bx = activeGlyph.bboxX * thumbW
  const by = activeGlyph.bboxY * thumbH
  const bw = activeGlyph.bboxW * thumbW
  const bh = activeGlyph.bboxH * thumbH

  return (
    <div style={{ position: 'relative', width: thumbW, height: thumbH,
      border: '0.5px solid #d4ccc0', borderRadius: 3, overflow: 'hidden' }}>
      <img src={page.imageUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      {/* highlight active glyph bbox */}
      <div style={{
        position: 'absolute',
        left: bx, top: by, width: bw, height: bh,
        border: '2px solid #9b2335',
        borderRadius: 2,
        boxShadow: '0 0 0 1px rgba(155,35,53,0.3)',
        pointerEvents: 'none',
      }} />
    </div>
  )
}

function NavBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{
      width: 28, height: 28, borderRadius: '50%', border: '0.5px solid #c4b9ae',
      background: '#faf5ec', cursor: 'pointer', fontSize: 16, display: 'flex',
      alignItems: 'center', justifyContent: 'center', color: '#120a02',
    }}>
      {children}
    </button>
  )
}
