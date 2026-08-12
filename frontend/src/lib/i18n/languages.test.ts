import { describe, expect, test } from 'vitest'

import {
  defaultLanguage,
  isLanguageCode,
  normalizeLanguageCode,
  supportedLanguages,
} from './languages'

describe('languages', () => {
  test('supported language codes are intentionally limited', () => {
    expect(supportedLanguages).toEqual(['en', 'ja'])
    expect(defaultLanguage).toBe('ja')
    expect(isLanguageCode('en')).toBe(true)
    expect(isLanguageCode('ja')).toBe(true)
    expect(isLanguageCode('fr')).toBe(false)
    expect(isLanguageCode('')).toBe(false)
    expect(isLanguageCode('EN')).toBe(false)
  })

  test('browser locale is normalized to supported primary subtags', () => {
    expect(normalizeLanguageCode('en-US')).toBe('en')
    expect(normalizeLanguageCode('ja-JP')).toBe('ja')
    expect(normalizeLanguageCode('fr-FR')).toBeNull()
  })
})
