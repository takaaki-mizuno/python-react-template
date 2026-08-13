import { describe, expect, test } from 'vitest'

import { formatUnixTimestampSeconds } from './formatters'

describe('formatters', () => {
  test('formatUnixTimestampSeconds uses the language-specific locale', () => {
    const value = 1786440600

    expect(formatUnixTimestampSeconds(value, 'ja')).toContain('2026')
    expect(formatUnixTimestampSeconds(value, 'en')).toMatch(/2026|Aug/)
    expect(formatUnixTimestampSeconds(value, 'ja')).not.toBe(
      formatUnixTimestampSeconds(value, 'en'),
    )
  })
})
