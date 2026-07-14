const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type UploadPageResult = {
  pageId: string
  pageNumber: number
  width: number
  height: number
  imageUrl: string
  status: 'processing' | 'completed' | 'failed'
}

export type PollPageResult<T = unknown> = {
  status: 'completed' | 'processing' | 'failed'
  glyphs: T[]
  message?: string
}


async function readErrorResponse(res: Response): Promise<string> {
  try {
    const data = await res.json()

    if (typeof data?.detail === 'string') {
      return data.detail
    }

    return JSON.stringify(data)
  } catch {
    return await res.text()
  }
}


export async function createCopybook(data: {
  title: string
  calligrapher: string
  dynasty?: string
  script: string
}) {
  const res = await fetch(`${BASE}/api/copybooks`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  if (!res.ok) {
    throw new Error(await readErrorResponse(res))
  }

  return res.json()
}


export async function uploadPage(
  copybookId: string,
  pageNumber: number,
  file: File,
  roi?: {
    left: number
    top: number
    right: number
    bottom: number
  },
): Promise<UploadPageResult> {
  const form = new FormData()

  form.append('file', file)
  form.append('page_number', String(pageNumber))

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

  const res = await fetch(
    `${BASE}/api/copybooks/${copybookId}/pages`,
    {
      method: 'POST',
      body: form,
    },
  )

  if (!res.ok) {
    throw new Error(await readErrorResponse(res))
  }

  return res.json()
}

export function imageUrl(path: string) {
  if (!path) return ''

  if (
    path.startsWith('http://') ||
    path.startsWith('https://') ||
    path.startsWith('blob:') ||
    path.startsWith('data:')
  ) {
    return path
  }

  return `${BASE}${path.startsWith('/') ? path : `/${path}`}`
}
