import { useState, useRef } from 'react'
import {
  createCopybook,
  imageUrl,
  pollPageProcessed,
  recognizePage,
  uploadPage,
} from '@/lib/api'
import type { ScannedPage, ScannedGlyph } from '@/types/practice'

type Step = 'form' | 'scanning' | 'review' | 'recognizing' | 'error'

interface Props {
  onScanComplete: (pages: ScannedPage[]) => void
}

const SCRIPTS = [
  { value: 'KAI',   label: '楷书' },
  { value: 'XING',  label: '行书' },
  { value: 'CAO',   label: '草书' },
  { value: 'LI',    label: '隶书' },
  { value: 'ZHUAN', label: '篆书' },
]

export function UploadPage({ onScanComplete }: Props) {
  const [step, setStep] = useState<Step>('form')
  const [scanMsg, setScanMsg] = useState('正在上传...')
  const [errorMsg, setErrorMsg] = useState('')
  const [progress, setProgress] = useState(0)
  const [copybookId, setCopybookId] = useState('')
  const [detectedPages, setDetectedPages] = useState<ScannedPage[]>([])

  // form state
  const [title,        setTitle]        = useState('')
  const [calligrapher, setCalligrapher] = useState('')
  const [dynasty,      setDynasty]      = useState('')
  const [script,       setScript]       = useState('KAI')
  const [files,        setFiles]        = useState<File[]>([])

  const fileRef = useRef<HTMLInputElement>(null)

  function onFilesChange(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    setFiles(picked)
  }

  async function handleSubmit() {
    if (!title || !calligrapher || files.length === 0) return
    setStep('scanning')
    setProgress(0)

    try {
      // 1. Create copybook
      setScanMsg('建立字帖档案...')
      const cb = await createCopybook({ title, calligrapher, dynasty: dynasty || undefined, script })
      setCopybookId(cb.id)

      // 2. Upload each page
      const scannedPages: ScannedPage[] = []
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        setScanMsg(`上传第 ${i + 1} / ${files.length} 页...`)
        setProgress(Math.round(((i) / files.length) * 40))

        const pageData = await uploadPage(cb.id, i + 1, file)

        // 3. Wait for OpenCV segmentation
        setScanMsg(`扫描第 ${i + 1} 页字形...`)
        setProgress(Math.round((40 + (i / files.length) * 50)))

        const detection = await pollPageProcessed<ScannedGlyph>(cb.id, pageData.pageId)
        if (detection.status !== 'completed') {
          throw new Error(detection.message ?? '字形检测尚未完成')
        }

        scannedPages.push({
          id:         pageData.pageId,
          pageNumber: pageData.pageNumber,
          imageUrl:   imageUrl(pageData.imageUrl),
          width:      pageData.width,
          height:     pageData.height,
          glyphs:     detection.glyphs.map((g: ScannedGlyph) => ({
            ...g,
            imageUrl: imageUrl(g.imageUrl),
          })),
        })
      }

      setProgress(100)
      setDetectedPages(scannedPages)
      setStep('review')

    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : '未知错误')
      setStep('error')
    }
  }

  async function handleRecognize() {
    setStep('recognizing')
    setProgress(0)

    try {
      const recognizedPages: ScannedPage[] = []

      for (let i = 0; i < detectedPages.length; i++) {
        const page = detectedPages[i]
        setScanMsg(`识别第 ${i + 1} / ${detectedPages.length} 页...`)
        setProgress(Math.round((i / detectedPages.length) * 100))

        const result = await recognizePage<ScannedGlyph>(copybookId, page.id)
        recognizedPages.push({
          ...page,
          glyphs: result.glyphs.map(glyph => ({
            ...glyph,
            imageUrl: imageUrl(glyph.imageUrl),
          })),
        })
      }

      setProgress(100)
      onScanComplete(recognizedPages)
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : '识字失败')
      setStep('error')
    }
  }

  // ── Scanning animation ────────────────────────────────────────────────────
  if (step === 'scanning' || step === 'recognizing') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-8"
        style={{ background: '#f5f1eb' }}>
        <div style={{ position: 'relative', width: 120, height: 120 }}>
          {/* ink drop animation */}
          <svg viewBox="0 0 120 120" width="120" height="120">
            <circle cx="60" cy="60" r="48" fill="none" stroke="#e8e0d4" strokeWidth="4" />
            <circle cx="60" cy="60" r="48" fill="none" stroke="#120a02" strokeWidth="4"
              strokeDasharray={`${progress * 3.015} 301.5`}
              strokeLinecap="round"
              style={{ transform: 'rotate(-90deg)', transformOrigin: '60px 60px', transition: 'stroke-dasharray 0.4s ease' }}
            />
          </svg>
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: "'Kaiti SC','KaiTi',serif", fontSize: 13, color: '#120a02',
          }}>
            {progress}%
          </div>
        </div>

        <div style={{ textAlign: 'center' }}>
          <p style={{ fontFamily: "'Kaiti SC','KaiTi',serif", fontSize: 18, color: '#120a02', marginBottom: 6 }}>
            {scanMsg}
          </p>
          <p style={{ fontSize: 12, color: '#9a8a78' }}>
            {step === 'scanning' ? '正在检测字形边框，请稍候' : '正在识别已确认的字形'}
          </p>
        </div>

        {/* scanning line animation */}
        <div style={{ width: 280, height: 2, background: '#e8e0d4', borderRadius: 1, overflow: 'hidden' }}>
          <div style={{
            height: '100%', background: '#9b2335', borderRadius: 1,
            width: `${progress}%`, transition: 'width 0.4s ease',
          }} />
        </div>
      </div>
    )
  }

  // ── Detection review ─────────────────────────────────────────────────────
  if (step === 'review') {
    return (
      <div className="flex-1 overflow-auto p-8" style={{ background: '#f5f1eb' }}>
        <div style={{ maxWidth: 980, margin: '0 auto' }}>
          <h2 style={{ fontFamily: "'Kaiti SC','KaiTi',serif", fontSize: 20, color: '#120a02' }}>
            检查字形边框
          </h2>
          <p style={{ margin: '6px 0 20px', fontSize: 13, color: '#76695c' }}>
            当前仅完成 YOLO 检测，尚未调用识字模型。确认边框后再开始识字。
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
            {detectedPages.map(page => (
              <div key={page.id} style={{ background: '#faf5ec', border: '1px solid #d4ccc0', borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 12, color: '#76695c', marginBottom: 8 }}>
                  第 {page.pageNumber} 页 · 检测到 {page.glyphs.length} 个字形
                </div>
                <div style={{ position: 'relative', lineHeight: 0 }}>
                  <img src={page.imageUrl} alt={`第 ${page.pageNumber} 页`} style={{ width: '100%', height: 'auto', display: 'block' }} />
                  {page.glyphs.map((glyph, index) => (
                    <div
                      key={glyph.id}
                      title={`顺序 ${index + 1}`}
                      style={{
                        position: 'absolute',
                        left: `${glyph.bboxX * 100}%`,
                        top: `${glyph.bboxY * 100}%`,
                        width: `${glyph.bboxW * 100}%`,
                        height: `${glyph.bboxH * 100}%`,
                        border: '1.5px solid #9b2335',
                        boxSizing: 'border-box',
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
            <button onClick={() => setStep('form')} style={{ ...btnStyle, background: '#76695c' }}>
              返回
            </button>
            <button onClick={handleRecognize} style={btnStyle}>
              确认边框并开始识字
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (step === 'error') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4" style={{ background: '#f5f1eb' }}>
        <p style={{ fontSize: 14, color: '#9b2335' }}>上传失败：{errorMsg}</p>
        <button onClick={() => setStep('form')} style={btnStyle}>重试</button>
      </div>
    )
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  const ready = title && calligrapher && files.length > 0

  return (
    <div className="flex-1 overflow-auto flex items-start justify-center p-10"
      style={{ background: '#f5f1eb' }}>
      <div style={{
        width: 480, background: '#faf5ec',
        border: '0.5px solid #d4ccc0', borderRadius: 8,
        padding: '32px 36px', boxShadow: '0 2px 16px rgba(0,0,0,0.07)',
      }}>
        <h2 style={{ fontFamily: "'Kaiti SC','KaiTi',serif", fontSize: 20, color: '#120a02', marginBottom: 24 }}>
          上传字帖
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Field label="字帖名称 *">
            <input style={inputStyle} value={title} onChange={e => setTitle(e.target.value)} placeholder="如：兰亭序" />
          </Field>

          <Field label="书法家 *">
            <input style={inputStyle} value={calligrapher} onChange={e => setCalligrapher(e.target.value)} placeholder="如：王羲之" />
          </Field>

          <Field label="朝代">
            <input style={inputStyle} value={dynasty} onChange={e => setDynasty(e.target.value)} placeholder="如：东晋" />
          </Field>

          <Field label="书体">
            <select style={inputStyle} value={script} onChange={e => setScript(e.target.value)}>
              {SCRIPTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>

          <Field label={`字帖图片 * ${files.length > 0 ? `（已选 ${files.length} 页）` : ''}`}>
            <div
              onClick={() => fileRef.current?.click()}
              style={{
                border: '1.5px dashed #c4b9ae', borderRadius: 6, padding: '20px 16px',
                textAlign: 'center', cursor: 'pointer', background: '#f5f1eb',
                transition: 'border-color 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#9b2335')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = '#c4b9ae')}
            >
              {files.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                  {files.map((f, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#9a8a78', background: '#ede8e0', borderRadius: 4, padding: '2px 8px' }}>
                      第{i+1}页 · {f.name}
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <p style={{ fontSize: 13, color: '#9a8a78', marginBottom: 4 }}>点击选择图片</p>
                  <p style={{ fontSize: 11, color: '#b8ae9e' }}>支持 JPG / PNG / TIFF，可多选（每个文件为一页）</p>
                </>
              )}
            </div>
            <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: 'none' }}
              onChange={onFilesChange} />
          </Field>
        </div>

        <button
          onClick={handleSubmit}
          disabled={!ready}
          style={{ ...btnStyle, width: '100%', marginTop: 28, opacity: ready ? 1 : 0.45 }}
        >
          开始扫描
        </button>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 12, color: '#9a8a78', display: 'block', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 6,
  border: '0.5px solid #c4b9ae', background: '#faf5ec',
  color: '#120a02', fontSize: 14, outline: 'none',
  fontFamily: "'Kaiti SC','KaiTi',serif",
}

const btnStyle: React.CSSProperties = {
  padding: '9px 24px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
  background: '#120a02', color: '#faf5ec', border: 'none', fontWeight: 500,
}
