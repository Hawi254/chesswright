import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Accordion, AccordionItem } from './accordion'

describe('Accordion', () => {
  it('renders defaultOpen items expanded and others collapsed', () => {
    render(
      <Accordion defaultOpen={['a']}>
        <AccordionItem value="a" title="Panel A"><p>Content A</p></AccordionItem>
        <AccordionItem value="b" title="Panel B"><p>Content B</p></AccordionItem>
      </Accordion>,
    )
    expect(screen.getByRole('button', { name: 'Panel A' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: 'Panel B' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('toggles panels independently -- multiple can be open at once', () => {
    render(
      <Accordion defaultOpen={[]}>
        <AccordionItem value="a" title="Panel A"><p>Content A</p></AccordionItem>
        <AccordionItem value="b" title="Panel B"><p>Content B</p></AccordionItem>
      </Accordion>,
    )
    const buttonA = screen.getByRole('button', { name: 'Panel A' })
    const buttonB = screen.getByRole('button', { name: 'Panel B' })
    expect(buttonA).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(buttonA)
    expect(buttonA).toHaveAttribute('aria-expanded', 'true')
    expect(buttonB).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(buttonB)
    expect(buttonA).toHaveAttribute('aria-expanded', 'true')
    expect(buttonB).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(buttonA)
    expect(buttonA).toHaveAttribute('aria-expanded', 'false')
    expect(buttonB).toHaveAttribute('aria-expanded', 'true')
  })

  it('always renders children content in the DOM, even while collapsed', () => {
    render(
      <Accordion defaultOpen={[]}>
        <AccordionItem value="a" title="Panel A"><p>Content A</p></AccordionItem>
      </Accordion>,
    )
    expect(screen.getByText('Content A')).toBeInTheDocument()
  })
})
