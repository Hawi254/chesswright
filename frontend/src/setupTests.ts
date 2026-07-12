import '@testing-library/jest-dom'

// jsdom has no ResizeObserver -- cmdk (via CommandList) uses it to track
// item sizes, and errors on mount without it. No-op stub is sufficient
// since these tests don't assert on layout/sizing behavior.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

// jsdom also has no scrollIntoView -- cmdk calls it when the highlighted
// item changes. No-op stub, same reasoning as ResizeObserver above.
Element.prototype.scrollIntoView = () => {}
