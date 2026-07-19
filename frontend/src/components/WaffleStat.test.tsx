import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import WaffleStat from './WaffleStat'

describe('WaffleStat', () => {
  it('renders exactly 100 cells', () => {
    const { container } = render(<WaffleStat percent={62} />)
    expect(container.querySelectorAll('[data-cell]')).toHaveLength(100)
  })

  it('fills a cell count matching the rounded percent', () => {
    const { container } = render(<WaffleStat percent={62.4} />)
    expect(container.querySelectorAll('[data-cell][data-filled="true"]')).toHaveLength(62)
  })

  it('rounds 0.5 up and clamps within 0-100', () => {
    const { container: c0 } = render(<WaffleStat percent={0} />)
    expect(c0.querySelectorAll('[data-filled="true"]')).toHaveLength(0)
    const { container: c100 } = render(<WaffleStat percent={100} />)
    expect(c100.querySelectorAll('[data-filled="true"]')).toHaveLength(100)
  })
})
