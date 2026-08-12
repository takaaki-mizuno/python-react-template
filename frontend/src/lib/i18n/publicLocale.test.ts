// @vitest-environment jsdom

import { describe, expect, test } from 'vitest'

import {
  detectPreferredPublicLanguage,
  localeFromPathname,
  stripLocaleFromPathname,
  withLocaleInPath,
} from './publicLocale'
import { writePublicLanguage } from './storage'

describe('publicLocale', () => {
  test('locale prefix is read and replaced without losing the inner path', () => {
    expect(localeFromPathname('/en/login')).toBe('en')
    expect(localeFromPathname('/ja/')).toBe('ja')
    expect(localeFromPathname('/fr/login')).toBeNull()
    expect(stripLocaleFromPathname('/en/login')).toBe('/login')
    expect(stripLocaleFromPathname('/ja/')).toBe('/')
    expect(withLocaleInPath('/ja/login', 'en')).toBe('/en/login')
    expect(withLocaleInPath('/', 'ja')).toBe('/ja/')
  })

  test('explicit public language preference wins over navigator language', () => {
    writePublicLanguage('en')

    expect(detectPreferredPublicLanguage()).toBe('en')
  })
})
