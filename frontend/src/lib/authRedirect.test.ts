// @vitest-environment jsdom

import { describe, expect, test } from 'vitest'

import { normalizeRedirectHref } from './authRedirect'

describe('normalizeRedirectHref', () => {
  test('same-origin の internal href を許可する', () => {
    expect(normalizeRedirectHref('/app')).toBe('/app')
    expect(normalizeRedirectHref('/app?tab=settings')).toBe('/app?tab=settings')
    expect(normalizeRedirectHref('/reports/2026.08#summary')).toBe(
      '/reports/2026.08#summary',
    )
  })

  test('外部 origin と危険な raw value は fallback へ落とす', () => {
    expect(normalizeRedirectHref('//evil.example')).toBe('/app')
    expect(normalizeRedirectHref('https://evil.example/app')).toBe('/app')
    expect(normalizeRedirectHref('/\\evil.example')).toBe('/app')
    expect(normalizeRedirectHref('/\tevil.example')).toBe('/app')
    expect(normalizeRedirectHref('/app\u0000/settings')).toBe('/app')
  })

  test('auth page 自己参照と空値は fallback へ落とす', () => {
    expect(normalizeRedirectHref('/login')).toBe('/app')
    expect(normalizeRedirectHref('/login/')).toBe('/app')
    expect(normalizeRedirectHref('/LOGIN')).toBe('/app')
    expect(normalizeRedirectHref('/login?redirect=/app')).toBe('/app')
    expect(normalizeRedirectHref('/register')).toBe('/app')
    expect(normalizeRedirectHref('/register/')).toBe('/app')
    expect(normalizeRedirectHref('/REGISTER/')).toBe('/app')
    expect(normalizeRedirectHref('')).toBe('/app')
    expect(normalizeRedirectHref(undefined)).toBe('/app')
    expect(normalizeRedirectHref(null)).toBe('/app')
  })
})
