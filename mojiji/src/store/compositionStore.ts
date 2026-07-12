import { create } from 'zustand'
import type { PaperType, GridType, ActiveCell } from '@/types'

export type PaperSize = 'a4' | 'liuchi' | 'sichi' | 'fangzhang'

interface CompositionState {
  text: string
  selections: Record<string, string | null>
  rows: number
  paper: PaperType
  paperSize: PaperSize
  grid: GridType
  practiceMode: boolean
  activeCell: ActiveCell | null

  setText: (text: string) => void
  setRows: (rows: number) => void
  setPaper: (paper: PaperType) => void
  setPaperSize: (size: PaperSize) => void
  setGrid: (grid: GridType) => void
  setPracticeMode: (v: boolean) => void
  setActiveCell: (cell: ActiveCell | null) => void
  selectGlyph: (character: string, glyphId: string) => void
}

export const useCompositionStore = create<CompositionState>((set) => ({
  text: '床前明月光疑是地上霜',
  selections: {},
  rows: 6,
  paper: 'xuan',
  paperSize: 'a4',
  grid: 'mi',
  practiceMode: false,
  activeCell: null,

  setText: (text) => set({ text, selections: {}, activeCell: null }),
  setRows: (rows) => set({ rows }),
  setPaper: (paper) => set({ paper }),
  setPaperSize: (paperSize) => set({ paperSize }),
  setGrid: (grid) => set({ grid }),
  setPracticeMode: (practiceMode) => set({ practiceMode, activeCell: practiceMode ? null : null }),
  setActiveCell: (activeCell) => set({ activeCell }),
  selectGlyph: (character, glyphId) =>
    set((s) => ({ selections: { ...s.selections, [character]: glyphId } })),
}))
