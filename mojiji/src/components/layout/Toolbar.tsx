import { useCompositionStore } from '@/store/compositionStore'
import type { GridType, PaperType } from '@/types'
import type { PaperSize } from '@/store/compositionStore'
import type { AppPage } from '@/App'

interface Props {
  currentPage: AppPage
  onNavigate: (page: AppPage) => void
}

export function Toolbar({ currentPage, onNavigate }: Props) {
  const {
    text, rows, paper, paperSize, grid, practiceMode,
    setText, setRows, setPaper, setPaperSize, setGrid, setPracticeMode,
  } = useCompositionStore()

  return (
    <header
      className="flex items-center gap-2 px-3 py-2 flex-shrink-0 flex-wrap"
      style={{ background: '#f0ece4', borderBottom: '0.5px solid #d4ccc0' }}
    >
      {/* logo */}
      <span className="font-kai text-base font-medium mr-2" style={{ color: '#120a02' }}>墨迹</span>

      {/* nav tabs */}
      <div style={{ display: 'flex', gap: 2, marginRight: 8 }}>
        {([
          { id: 'compose',  label: '创作' },
          { id: 'upload',   label: '上传字帖' },
        ] as { id: AppPage; label: string }[]).map(tab => (
          <button key={tab.id} onClick={() => onNavigate(tab.id)}
            style={{
              padding: '3px 10px', borderRadius: 4, fontSize: 12, cursor: 'pointer', border: 'none',
              background: currentPage === tab.id ? '#120a02' : 'transparent',
              color:      currentPage === tab.id ? '#faf5ec' : '#9a8a78',
            }}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* compose-only controls */}
      {currentPage === 'compose' && (
        <>
          <div style={{ width: '0.5px', height: 18, background: '#c4b9ae' }} />

          <input type="text" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="输入诗词内容..."
            className="flex-1 min-w-32 max-w-xs px-2.5 py-1 rounded text-sm outline-none font-kai"
            style={{ background: '#faf5ec', border: '0.5px solid #c4b9ae', color: '#120a02' }}
          />

          <Select value={String(rows)} onChange={(v) => setRows(Number(v))} options={[
            { value: '4', label: '4 行' }, { value: '5', label: '5 行' },
            { value: '6', label: '6 行' }, { value: '8', label: '8 行' },
            { value: '10', label: '10 行' },
          ]} />

          <Select value={grid} onChange={(v) => setGrid(v as GridType)} options={[
            { value: 'mi', label: '米字格' }, { value: 'jiu', label: '九宫格' }, { value: 'none', label: '无格' },
          ]} />

          <Select value={paper} onChange={(v) => setPaper(v as PaperType)} options={[
            { value: 'xuan', label: '宣纸' }, { value: 'red', label: '朱砂' }, { value: 'dark', label: '乌金' },
          ]} />

          <Select value={paperSize} onChange={(v) => setPaperSize(v as PaperSize)} options={[
            { value: 'a4', label: 'A4' }, { value: 'sichi', label: '四尺' },
            { value: 'liuchi', label: '六尺' }, { value: 'fangzhang', label: '丈二' },
          ]} />

          <div style={{ width: '0.5px', height: 18, background: '#c4b9ae' }} />

          <button onClick={() => setPracticeMode(!practiceMode)} style={{
            padding: '4px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            border: practiceMode ? 'none' : '0.5px solid #c4b9ae',
            background: practiceMode ? '#9b2335' : '#faf5ec',
            color: practiceMode ? '#faf5ec' : '#120a02',
            fontWeight: practiceMode ? 500 : 400, transition: 'all 0.15s',
          }}>
            {practiceMode ? '✦ 练习中' : '练习'}
          </button>
        </>
      )}

      {/* practice page indicator */}
      {currentPage === 'practice' && (
        <span style={{ fontSize: 12, color: '#9a8a78' }}>临帖模式</span>
      )}
    </header>
  )
}

function Select({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="px-2 py-1 rounded text-xs outline-none cursor-pointer"
      style={{ background: '#faf5ec', border: '0.5px solid #c4b9ae', color: '#120a02' }}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}
