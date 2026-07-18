// @vitest-environment jsdom

import { afterEach, expect, test, vi } from 'vitest'

import { apiClient } from './apiClient'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('unsafe request では csrf header を付与する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'

  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/auth/login', {
    email: 'user@example.com',
    password: 'Password123!',
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/login',
    expect.objectContaining({
      credentials: 'include',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf-123',
      }),
    }),
  )
})

test('non-2xx response では ApiError を投げる', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  await expect(apiClient.get('/api/auth/me')).rejects.toEqual(
    expect.objectContaining({
      status: 401,
      body: { message: 'Unauthorized' },
    }),
  )
})

test('csrf bootstrap 失敗時は unsafe request を送信しない', async () => {
  document.cookie = 'csrf_token=stale-token; path=/'
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'CSRF unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await expect(
    apiClient.post('/api/auth/login', {
      email: 'user@example.com',
      password: 'Password123!',
    }),
  ).rejects.toEqual(
    expect.objectContaining({
      status: 503,
      body: { detail: 'CSRF unavailable' },
    }),
  )
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(fetchMock).toHaveBeenCalledWith('/api/auth/csrf', {
    credentials: 'include',
  })
})
