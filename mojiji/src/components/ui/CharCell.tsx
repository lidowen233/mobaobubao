import { buildGridPath, buildDiagPath, PAPER_COLORS, PAPER_INK, PAPER_BORDER, GRID_COLOR } from '@/lib/grid'
import type { GridType, PaperType } from '@/types'

interface Props {
  displayChar: string
  size: number
  grid: GridType
  paper: PaperType
  practiceMode: boolean  // controls whether cell border + grid lines show
  active?: boolean
  empty?: boolean
  onClick?: () => void
}

export function CharCell({ displayChar, size, grid, paper, practiceMode, active, empty, onClick }: Props) {
  const bg        = PAPER_COLORS[paper]
  const ink       = PAPER_INK[paper]
  const gridColor = GRID_COLOR[paper]
  const fontSize  = Math.round(size * 0.72)

  // Border: only visible in practice mode (or when active)
  const borderColor = active ? '#9b2335' : practiceMode ? PAPER_BORDER[paper] : 'transparent'
  const borderWidth = active ? 2 : 1

  // Grid lines: only in practice mode
  const showGrid    = practiceMode && grid !== 'none'
  const solidPath   = buildGridPath(grid, size)
  const diagPath    = grid === 'mi' ? buildDiagPath(size) : ''

  if (empty) {
    return (
      <div style={{ width: size, height: size, background: 'transparent' }} className="flex-shrink-0" />
    )
  }

  return (
    <div
      onClick={onClick}
      style={{ width: size, height: size, background: bg, borderColor: borderColor, borderWidth: borderWidth }}
      className="rounded-sm border relative flex items-center justify-center flex-shrink-0 cursor-pointer transition-transform hover:scale-[1.04]"
    >
      {showGrid && (
        <svg
          viewBox={`0 0 ${size} ${size}`}
          width={size} height={size}
          className="absolute inset-0 pointer-events-none"
        >
          {solidPath && (
            <path d={solidPath} stroke={gridColor} strokeWidth="0.9" opacity="0.35" fill="none" />
          )}
          {diagPath && (
            <path d={diagPath} stroke={gridColor} strokeWidth="0.65" opacity="0.2" fill="none" strokeDasharray="4 3" />
          )}
        </svg>
      )}
      <span className="font-kai relative z-10 select-none leading-none" style={{ fontSize, color: ink }}>
        {displayChar}
      </span>
    </div>
  )
}
