// @vitest-environment jsdom

import { afterEach, describe, expect, test, vi } from 'vitest'

import {
  clearLastResolvedLanguage,
  readLastResolvedLanguage,
  readPublicLanguage,
  writeLastResolvedLanguage,
  writePublicLanguage,
} from './storage'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('i18n storage', () => {
  test('read/write/remove supported language codes', () => {
    writePublicLanguage('en')
    writeLastResolvedLanguage('ja')

    expect(readPublicLanguage()).toBe('en')
    expect(readLastResolvedLanguage()).toBe('ja')

    clearLastResolvedLanguage()

    expect(readLastResolvedLanguage()).toBeNull()
  })

  test('localStorage failures are swallowed and fall back to null', () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    vi.spyOn(window.localStorage, 'removeItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })

    expect(() => writePublicLanguage('en')).not.toThrow()
    expect(() => writeLastResolvedLanguage('ja')).not.toThrow()
    expect(() => clearLastResolvedLanguage()).not.toThrow()
    expect(readPublicLanguage()).toBeNull()
    expect(readLastResolvedLanguage()).toBeNull()
  })
})
