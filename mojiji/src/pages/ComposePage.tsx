import { useResizablePanel } from '@/hooks/useResizablePanel'
import { PaperGrid } from '@/components/ui/PaperGrid'
import { PreviewPanel } from '@/components/ui/PreviewPanel'

export function ComposePage() {
  // Right panel starts at 240px; drag divider left to widen, right to narrow
  const { width: previewWidth, onMouseDown } = useResizablePanel(240, 160, 480)

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* left: paper canvas — takes remaining space */}
      <PaperGrid />

      {/* drag divider */}
      <div
        onMouseDown={onMouseDown}
        className="w-1.5 flex-shrink-0 cursor-col-resize flex items-center justify-center group select-none"
        style={{ background: '#d4ccc0' }}
      >
        <div
          className="w-0.5 h-8 rounded-full opacity-40 group-hover:opacity-100 transition-opacity"
          style={{ background: '#9b2335' }}
        />
      </div>

      {/* right: preview panel */}
      <div
        className="flex-shrink-0 overflow-hidden"
        style={{ width: previewWidth, borderLeft: '0.5px solid #d4ccc0', background: '#f5f1eb' }}
      >
        <PreviewPanel />
      </div>
    </div>
  )
}
