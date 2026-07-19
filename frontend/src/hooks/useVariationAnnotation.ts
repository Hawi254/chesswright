import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface Annotation {
  id: string
  move_index: number
  glyph: string | null
  comment: string | null
  ai_comment: string | null
  ai_model: string | null
  generated_at: string | null
  variation_id: string | null
  game_id: string | null
}

export interface UseAnnotationResult {
  annotation: Annotation | null
  loading: boolean
  save: (glyph: string | null, comment: string | null) => void
  saveError: string | null
  askClaude: (evalCp: number | null, bestMoveSan: string | null, userComment: string | null) => void
  aiLoading: boolean
  aiError: string | null
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export function useVariationAnnotation(
  variationId: string | null,
  step: number,
  fen: string | null,
): UseAnnotationResult {
  const [annotation, setAnnotation] = useState<Annotation | null>(null)
  const [loading, setLoading] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)

  useEffect(() => {
    setSaveError(null)
    setAiError(null)
    if (!variationId) {
      setAnnotation(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/api/variations/${variationId}/annotations/${step}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<Annotation | null>
      })
      .then((body) => {
        if (cancelled) return
        setAnnotation(body)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setAnnotation(null)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [variationId, step])

  function save(glyph: string | null, comment: string | null) {
    if (!variationId) return
    setSaveError(null)
    fetch(`${API_BASE}/api/variations/${variationId}/annotations/${step}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ glyph, comment }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<Annotation>
      })
      .then((body) => setAnnotation(body))
      .catch(() => setSaveError('Failed to save annotation. Try again.'))
  }

  function askClaude(evalCp: number | null, bestMoveSan: string | null, userComment: string | null) {
    if (!variationId || !fen) return
    setAiLoading(true)
    setAiError(null)
    fetch(`${API_BASE}/api/variations/${variationId}/annotations/${step}/ai-comment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen, eval_cp: evalCp, best_move_san: bestMoveSan, user_comment: userComment }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorDetail(r))
        return r.json() as Promise<Annotation>
      })
      .then((body) => {
        setAnnotation(body)
        setAiLoading(false)
      })
      .catch((err: Error) => {
        setAiLoading(false)
        setAiError(err.message)
      })
  }

  return { annotation, loading, save, saveError, askClaude, aiLoading, aiError }
}
