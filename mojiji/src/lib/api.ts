const BASE =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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

  if (roi) {
    form.append('roi_left', String(roi.left))
    form.append('roi_top', String(roi.top))
    form.append('roi_right', String(roi.right))
    form.append('roi_bottom', String(roi.bottom))
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


export async function getPageGlyphs(
  copybookId: string,
  pageId: string,
) {
  const res = await fetch(
    `${BASE}/api/copybooks/${copybookId}/pages/${pageId}/glyphs`,
    {
      cache: 'no-store',
    },
  )

  if (!res.ok) {
    throw new Error(await readErrorResponse(res))
  }

  return res.json()
}


export async function getPage(
  copybookId: string,
  pageId: string,
): Promise<{ processed: boolean }> {
  const res = await fetch(
    `${BASE}/api/copybooks/${copybookId}/pages/${pageId}`,
    { cache: 'no-store' },
  )

  if (!res.ok) {
    throw new Error(await readErrorResponse(res))
  }

  return res.json()
}


export async function recognizePage<T = unknown>(
  copybookId: string,
  pageId: string,
): Promise<{ status: 'completed'; glyphs: T[] }> {
  const res = await fetch(
    `${BASE}/api/copybooks/${copybookId}/pages/${pageId}/recognize`,
    { method: 'POST' },
  )

  if (!res.ok) {
    throw new Error(await readErrorResponse(res))
  }

  return res.json()
}


function sleep(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}


export async function pollPageProcessed<T = unknown>(
  copybookId: string,
  pageId: string,
  options: {
    maxWaitMs?: number
    intervalMs?: number
    signal?: AbortSignal
    onProgress?: (elapsedMs: number) => void
  } = {},
): Promise<PollPageResult<T>> {
  const {
    maxWaitMs = 5 * 60 * 1000,
    intervalMs = 2000,
    signal,
    onProgress,
  } = options

  const startedAt = Date.now()
  let consecutiveErrors = 0

  while (Date.now() - startedAt < maxWaitMs) {
    if (signal?.aborted) {
      throw new DOMException(
        'Polling was cancelled',
        'AbortError',
      )
    }

    const elapsedMs = Date.now() - startedAt
    onProgress?.(elapsedMs)

    try {
      const page = await getPage(copybookId, pageId)

      consecutiveErrors = 0

      if (page.processed) {
        const glyphs = await getPageGlyphs(copybookId, pageId)
        return {
          status: 'completed',
          glyphs,
        }
      }
    } catch (error) {
      consecutiveErrors += 1

      console.warn(
        `[segmentation] Polling attempt failed (${consecutiveErrors})`,
        error,
      )

      // Temporary network failures should not immediately fail processing.
      if (consecutiveErrors >= 5) {
        return {
          status: 'failed',
          glyphs: [],
          message:
            error instanceof Error
              ? error.message
              : 'Unable to check segmentation status.',
        }
      }
    }

    await sleep(intervalMs)
  }

  // The upload succeeded. Processing is simply taking longer than expected.
  return {
    status: 'processing',
    glyphs: [],
    message:
      'The page was uploaded successfully. Segmentation is still processing.',
  }
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
