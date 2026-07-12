import { useCompositionStore } from '@/store/compositionStore'
import { getGlyphsForChar } from '@/lib/mockData'
import { PAPER_COLORS, PAPER_BORDER, PAPER_SIZES } from '@/lib/grid'
import { CharCell } from './CharCell'

const CELL_SIZE = 72
const CELL_GAP  = 4

export function PaperGrid() {
  const { text, rows, paper, paperSize, grid, practiceMode, activeCell, setActiveCell, selections } = useCompositionStore()

  const chars = [...text.replace(/\s/g, '')]
  const numCols = Math.ceil(chars.length / rows)

  const columns: (string | null)[][] = []
  for (let c = 0; c < numCols; c++) {
    const col: (string | null)[] = []
    for (let r = 0; r < rows; r++) {
      const i = c * rows + r
      col.push(i < chars.length ? chars[i] : null)
    }
    columns.push(col)
  }

  const { w, h } = PAPER_SIZES[paperSize]
  const sheetH = Math.min(window.innerHeight - 100, 700)
  const sheetW = Math.round((w / h) * sheetH)

  const bg     = PAPER_COLORS[paper]
  const borderColor = PAPER_BORDER[paper]

  return (
    <div className="flex-1 overflow-auto flex items-start justify-center p-8">
      <div
        style={{
          width: sheetW,
          minHeight: sheetH,
          background: bg,
          border: `1px solid ${borderColor}`,
          boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
          borderRadius: 2,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'flex-end',
          padding: 20,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'row-reverse', gap: CELL_GAP, alignItems: 'flex-start' }}>
          {columns.map((col, ci) => (
            <div key={ci} style={{ display: 'flex', flexDirection: 'column', gap: CELL_GAP }}>
              {col.map((ch, ri) => {
                const charIdx = ci * rows + ri
                if (!ch) return (
                  <CharCell key={ri} displayChar="" size={CELL_SIZE} grid={grid} paper={paper} empty practiceMode={practiceMode} />
                )
                const glyphs = getGlyphsForChar(ch)
                const selGlyphId = selections[ch]
                const selGlyph = glyphs.find((g) => g.id === selGlyphId) ?? glyphs[0]
                const displayChar = selGlyph?.character ?? ch
                const isActive = activeCell?.charIndex === charIdx

                return (
                  <CharCell
                    key={ri}
                    displayChar={displayChar}
                    size={CELL_SIZE}
                    grid={grid}
                    paper={paper}
                    practiceMode={practiceMode}
                    active={isActive}
                    onClick={() => setActiveCell({ charIndex: charIdx, character: ch })}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
