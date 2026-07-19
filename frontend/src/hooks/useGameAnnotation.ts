import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { Annotation, UseAnnotationResult } from './useVariationAnnotation'

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export function useGameAnnotation(
  gameId: string,
  ply: number | null,
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
    if (ply === null) {
      setAnnotation(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/api/games/${gameId}/annotations/${ply}`)
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
  }, [gameId, ply])

  function save(glyph: string | null, comment: string | null) {
    if (ply === null) return
    setSaveError(null)
    fetch(`${API_BASE}/api/games/${gameId}/annotations/${ply}`, {
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
    if (ply === null || !fen) return
    setAiLoading(true)
    setAiError(null)
    fetch(`${API_BASE}/api/games/${gameId}/annotations/${ply}/ai-comment`, {
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
