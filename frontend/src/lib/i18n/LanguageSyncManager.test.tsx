// @vitest-environment jsdom

import { cleanup, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import i18n from './i18n'
import { LanguageSyncManager } from './LanguageSyncManager'
import { resolveLanguage } from './languageResolver'
import {
  readLastResolvedLanguage,
  writeLastResolvedLanguage,
  writePublicLanguage,
} from './storage'
import type { AuthUser } from '@/lib/authApi'

let pathname = '/app'
let user: AuthUser | null = null

vi.mock('@tanstack/react-router', () => ({
  useRouterState: vi.fn(({ select }) => select({ location: { pathname } })),
}))

vi.mock('@/hooks/useAuthSession', () => ({
  useAuthSession: () => ({ user }),
}))

describe('LanguageSyncManager resolution', () => {
  beforeEach(async () => {
    cleanup()
    window.localStorage.clear()
    pathname = '/app'
    user = null
    await i18n.changeLanguage('ja')
  })

  test('public localized route wins over authenticated user preference', () => {
    expect(resolveLanguage('/ja/', 'en')).toBe('ja')
  })

  test('authenticated route uses user preference when URL has no locale', () => {
    expect(resolveLanguage('/app/settings', 'en')).toBe('en')
  })

  test('public preference wins over last render hint for anonymous locale-less routes', () => {
    writeLastResolvedLanguage('ja')
    writePublicLanguage('en')

    expect(resolveLanguage('/forbidden', null)).toBe('en')
  })

  test('anonymous locale-less route falls back to browser preference after storage hints', () => {
    vi.stubGlobal('navigator', {
      language: 'en-US',
      languages: ['en-US', 'ja-JP'],
    })

    expect(resolveLanguage('/forbidden', null)).toBe('en')
  })

  test('route, auth cache, storage event の変化を i18n language と render hint に反映する', async () => {
    pathname = '/ja/'
    user = authUser('en')
    const { rerender } = render(<LanguageSyncManager />)

    await waitFor(() => expect(i18n.language).toBe('ja'))
    expect(readLastResolvedLanguage()).toBe('ja')

    pathname = '/app/settings'
    rerender(<LanguageSyncManager />)

    await waitFor(() => expect(i18n.language).toBe('en'))
    expect(readLastResolvedLanguage()).toBe('en')

    user = null
    pathname = '/forbidden'
    rerender(<LanguageSyncManager />)
    writePublicLanguage('ja')

    await waitFor(() => expect(i18n.language).toBe('ja'))
    expect(readLastResolvedLanguage()).toBe('ja')
  })
})

function authUser(languageCode: AuthUser['languageCode']): AuthUser {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    languageCode,
    roles: [],
    permissions: [],
  }
}
