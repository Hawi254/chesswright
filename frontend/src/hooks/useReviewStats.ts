import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface ReviewCounts { total: number; due: number; new: number }
export interface WeeklyRecallPoint { week: string; n_reviews: number; recall_pct: number }
export interface LearningCurvePoint { nth_review: string; n_reviews: number; recall_pct: number }
export interface RecallBySourcePoint { source: string; n_reviews: number; recall_pct: number }

export interface ReviewStats {
  counts: ReviewCounts
  weekly_recall: WeeklyRecallPoint[]
  learning_curve: LearningCurvePoint[]
  recall_by_source: RecallBySourcePoint[]
}

export function useReviewStats(enabled: boolean, refreshKey: number) {
  const [stats, setStats] = useState<ReviewStats | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    fetch(`${API_BASE}/api/training/review/stats`)
      .then((r) => r.json())
      .then((body: ReviewStats) => { if (!cancelled) setStats(body) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [enabled, refreshKey])

  return stats
}
