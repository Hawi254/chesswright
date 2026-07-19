import { describe, expect, it } from 'vitest'
import { POINTS_BUCKET_COLOR, POINTS_BUCKET_LABEL, POINTS_REASON_LABEL } from './pointsLabels'

describe('pointsLabels', () => {
  it('has a display label for each of the three raw bucket keys', () => {
    expect(POINTS_BUCKET_LABEL.failed_conversion).toBe('Failed conversion')
    expect(POINTS_BUCKET_LABEL.missed_swindle).toBe('Missed swindle')
    expect(POINTS_BUCKET_LABEL.failed_hold).toBe('Failed hold')
  })

  it('assigns a distinct color to each bucket', () => {
    const colors = [POINTS_BUCKET_COLOR.failed_conversion, POINTS_BUCKET_COLOR.missed_swindle, POINTS_BUCKET_COLOR.failed_hold]
    expect(new Set(colors).size).toBe(3)
  })

  it('has a display label for each failed-conversion cause reason', () => {
    expect(POINTS_REASON_LABEL.hung_piece).toBe('Hung a piece')
    expect(POINTS_REASON_LABEL.blown_mate).toBe('Blew a forced mate')
    expect(POINTS_REASON_LABEL.time_pressure).toBe('Time pressure')
    expect(POINTS_REASON_LABEL.other).toBe('Other / gradual give-back')
  })
})
