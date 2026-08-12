import { describe, expect, test } from 'vitest'

import { formatDateTime } from './formatters'

describe('formatters', () => {
  test('formatDateTime uses the language-specific locale', () => {
    const value = '2026-08-11T09:30:00Z'

    expect(formatDateTime(value, 'ja')).toContain('2026')
    expect(formatDateTime(value, 'en')).toMatch(/2026|Aug/)
    expect(formatDateTime(value, 'ja')).not.toBe(formatDateTime(value, 'en'))
  })
})
