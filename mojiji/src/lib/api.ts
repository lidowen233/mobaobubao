const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function createCopybook(data: {
  title: string
  calligrapher: string
  dynasty?: string
  script: string
}) {
  const res = await fetch(`${BASE}/api/copybooks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function uploadPage(copybookId: string, pageNumber: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('page_number', String(pageNumber))
  const res = await fetch(`${BASE}/api/copybooks/${copybookId}/pages`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getPageGlyphs(copybookId: string, pageId: string) {
  const res = await fetch(`${BASE}/api/copybooks/${copybookId}/pages/${pageId}/glyphs`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function pollPageProcessed(copybookId: string, pageId: string, maxWaitMs = 300000) {
  const interval = 3000
  const start = Date.now()
  while (Date.now() - start < maxWaitMs) {
    await new Promise(r => setTimeout(r, interval))
    const glyphs = await getPageGlyphs(copybookId, pageId)
    if (glyphs.length > 0) return glyphs
  }
  throw new Error('Segmentation timed out')
}
export function imageUrl(path: string) {
  if (path.startsWith('http')) return path
  return `${BASE}${path}`
}
