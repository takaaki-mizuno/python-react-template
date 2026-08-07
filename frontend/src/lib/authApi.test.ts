// @vitest-environment jsdom

import { afterEach, expect, test, vi } from 'vitest'

import {
  deleteCurrentAccount,
  fetchOidcProviders,
  startOidcLogin,
  startOidcReauth,
} from './authApi'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('deleteCurrentAccount は camelCase body で DELETE /api/auth/me を呼ぶ', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await deleteCurrentAccount({
    confirmEmail: 'user@example.com',
    password: 'Password123!',
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/me',
    expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({
        confirmEmail: 'user@example.com',
        password: 'Password123!',
      }),
    }),
  )
  const init = fetchMock.mock.calls[0][1] as RequestInit
  const headers = new Headers(init.headers)
  expect(headers.get('x-csrf-token')).toBe('csrf-123')
})

test('fetchOidcProviders は providerId と displayName だけを読む', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          providers: [{ providerId: 'google', displayName: 'Google' }],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ),
  )

  await expect(fetchOidcProviders()).resolves.toEqual([
    { providerId: 'google', displayName: 'Google' },
  ])
})

test('startOidcLogin は redirect を壊さず start endpoint へ遷移する', () => {
  const assign = vi.fn()

  startOidcLogin('google', '/app/settings?tab=danger#delete', assign)

  expect(assign).toHaveBeenCalledWith(
    '/api/auth/oidc/google/start?redirect=%2Fapp%2Fsettings%3Ftab%3Ddanger%23delete',
  )
})

test('startOidcReauth は redirect を壊さず reauth endpoint へ遷移する', () => {
  const assign = vi.fn()

  startOidcReauth('google', '/app/settings?tab=danger#delete', assign)

  expect(assign).toHaveBeenCalledWith(
    '/api/auth/oidc/google/reauth?redirect=%2Fapp%2Fsettings%3Ftab%3Ddanger%23delete',
  )
})
