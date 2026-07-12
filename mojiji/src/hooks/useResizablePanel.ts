import { useCallback, useEffect, useRef, useState } from 'react'

// Controls the RIGHT panel width by dragging the divider.
// Dragging right → narrower preview; dragging left → wider preview.
export function useResizablePanel(initialWidth: number, min = 160, max = 500) {
  const [width, setWidth] = useState(initialWidth)
  const dragging = useRef(false)
  const startX   = useRef(0)
  const startW   = useRef(0)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    startX.current   = e.clientX
    startW.current   = width
    e.preventDefault()
  }, [width])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      // divider is between left and right panels:
      // moving left (negative dx) → right panel gets wider
      const dx = e.clientX - startX.current
      setWidth(Math.max(min, Math.min(max, startW.current - dx)))
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [min, max])

  return { width, onMouseDown }
}
