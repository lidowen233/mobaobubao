import { useState } from 'react'
import { Toolbar } from '@/components/layout/Toolbar'
import { ComposePage } from '@/pages/ComposePage'
import { UploadPage } from '@/pages/UploadPage'
import { PracticePage } from '@/pages/PracticePage'
import type { ScannedPage } from '@/types/practice'

export type AppPage = 'compose' | 'upload' | 'practice'

export default function App() {
  const [page, setPage] = useState<AppPage>('compose')
  const [practicePages, setPracticePages] = useState<ScannedPage[]>([])

  function onScanComplete(pages: ScannedPage[]) {
    setPracticePages(pages)
    setPage('practice')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Toolbar currentPage={page} onNavigate={setPage} />
      {page === 'compose'  && <ComposePage />}
      {page === 'upload'   && <UploadPage onScanComplete={onScanComplete} />}
      {page === 'practice' && <PracticePage pages={practicePages} onBack={() => setPage('upload')} />}
    </div>
  )
}
