import { beforeEach, vi } from 'vitest'

import i18n from '@/lib/i18n/i18n'

class ResizeObserverMock implements ResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  configurable: true,
  value: ResizeObserverMock,
})

if (typeof Element !== 'undefined') {
  Object.defineProperty(Element.prototype, 'hasPointerCapture', {
    configurable: true,
    value: vi.fn(() => false),
  })

  Object.defineProperty(Element.prototype, 'setPointerCapture', {
    configurable: true,
    value: vi.fn(),
  })

  Object.defineProperty(Element.prototype, 'releasePointerCapture', {
    configurable: true,
    value: vi.fn(),
  })

  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
}

if (typeof navigator !== 'undefined') {
  Object.defineProperty(navigator, 'languages', {
    configurable: true,
    value: ['ja-JP'],
  })
  Object.defineProperty(navigator, 'language', {
    configurable: true,
    value: 'ja-JP',
  })
}

beforeEach(async () => {
  try {
    if (typeof window !== 'undefined') {
      ensureLocalStorage()
      window.localStorage.clear()
    }
  } catch {
    // Some unit tests intentionally simulate unavailable browser storage.
  }
  await i18n.changeLanguage('ja')
})

function ensureLocalStorage(): void {
  try {
    window.localStorage.clear()
    return
  } catch {
    // Install an in-memory replacement when jsdom cannot provide localStorage.
  }

  const values = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      clear: () => values.clear(),
      getItem: (key: string) => values.get(key) ?? null,
      removeItem: (key: string) => values.delete(key),
      setItem: (key: string, value: string) => values.set(key, value),
    },
  })
}
