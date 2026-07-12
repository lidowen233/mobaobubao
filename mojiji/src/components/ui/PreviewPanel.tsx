import { useCompositionStore } from '@/store/compositionStore'
import { getGlyphsForChar, getCopybookById } from '@/lib/mockData'
import { buildGridPath, buildDiagPath, PAPER_COLORS, PAPER_INK, GRID_COLOR } from '@/lib/grid'

const PREVIEW_SIZE = 180

export function PreviewPanel() {
  const { activeCell, grid, paper, selections, selectGlyph, text, setActiveCell } = useCompositionStore()

  const chars = [...text.replace(/\s/g, '')]
  const total = chars.length

  function navChar(dir: number) {
    if (!chars.length) return
    const cur = activeCell?.charIndex ?? 0
    const next = (cur + dir + total) % total
    setActiveCell({ charIndex: next, character: chars[next] })
  }

  const bg        = PAPER_COLORS[paper]
  const ink       = PAPER_INK[paper]
  const gridColor = GRID_COLOR[paper]

  if (!activeCell) {
    return (
      <div className="flex flex-col h-full items-center justify-center gap-3 px-5">
        <span className="font-kai select-none" style={{ fontSize: 64, color: '#120a02', opacity: 0.1 }}>字</span>
        <p className="text-xs text-center leading-relaxed" style={{ color: '#9a8a78' }}>
          点击左边的字<br />在此预览并选择字形
        </p>
      </div>
    )
  }

  const { character, charIndex } = activeCell
  const glyphs = getGlyphsForChar(character)
  const selGlyphId = selections[character]
  const selGlyph = glyphs.find((g) => g.id === selGlyphId) ?? glyphs[0]
  const displayChar = selGlyph?.character ?? character

  const solidPath = buildGridPath(grid, PREVIEW_SIZE)
  const diagPath  = grid === 'mi' ? buildDiagPath(PREVIEW_SIZE) : ''

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between px-3 py-2 border-b text-xs flex-shrink-0"
        style={{ borderColor: '#d4ccc0', color: '#9a8a78' }}>
        <span className="font-kai text-base font-medium" style={{ color: '#120a02' }}>「{character}」</span>
        <span>{charIndex + 1} / {total}</span>
      </div>

      {/* large preview — always shows grid */}
      <div className="flex justify-center pt-4 flex-shrink-0">
        <div className="relative flex items-center justify-center rounded"
          style={{ width: PREVIEW_SIZE, height: PREVIEW_SIZE, background: bg, border: `1.5px solid ${gridColor}44` }}>
          {grid !== 'none' && (
            <svg viewBox={`0 0 ${PREVIEW_SIZE} ${PREVIEW_SIZE}`} width={PREVIEW_SIZE} height={PREVIEW_SIZE}
              className="absolute inset-0 pointer-events-none">
              {solidPath && <path d={solidPath} stroke={gridColor} strokeWidth="1" opacity="0.35" fill="none" />}
              {diagPath  && <path d={diagPath}  stroke={gridColor} strokeWidth="0.7" opacity="0.2"  fill="none" strokeDasharray="4 3" />}
            </svg>
          )}
          <span className="font-kai relative z-10 select-none leading-none" style={{ fontSize: 130, color: ink }}>
            {displayChar}
          </span>
        </div>
      </div>

      {/* nav */}
      <div className="flex items-center justify-center gap-3 py-2 flex-shrink-0">
        <button onClick={() => navChar(-1)}
          className="w-7 h-7 rounded-full border flex items-center justify-center text-sm hover:bg-black/5 transition-colors"
          style={{ borderColor: '#c4b9ae' }}>‹</button>
        <span className="text-xs" style={{ color: '#9a8a78' }}>上一字 / 下一字</span>
        <button onClick={() => navChar(1)}
          className="w-7 h-7 rounded-full border flex items-center justify-center text-sm hover:bg-black/5 transition-colors"
          style={{ borderColor: '#c4b9ae' }}>›</button>
      </div>

      {/* glyph picker */}
      <div className="flex-shrink-0 px-3 pb-1 text-xs" style={{ color: '#9a8a78', borderTop: '0.5px solid #d4ccc0', paddingTop: 6 }}>
        字形来源
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 flex flex-col gap-2">
        {glyphs.map((g) => {
          const cb = getCopybookById(g.copybookId)
          const isSelected = g.id === (selGlyphId ?? glyphs[0]?.id)
          return (
            <button key={g.id} onClick={() => selectGlyph(character, g.id)}
              className="w-full rounded border-[1.5px] py-1 flex flex-col items-center gap-0.5 transition-colors"
              style={{ background: isSelected ? '#fdf3f1' : '#faf5ec', borderColor: isSelected ? '#9b2335' : '#d4ccc0' }}>
              <span className="font-kai leading-none select-none" style={{ fontSize: 34, color: '#120a02' }}>
                {g.character}
              </span>
              {cb && <span className="text-[10px]" style={{ color: '#9a8a78' }}>{cb.calligrapher}·{cb.title}</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
