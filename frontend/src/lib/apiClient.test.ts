// @vitest-environment jsdom

import { afterEach, expect, test, vi } from 'vitest'

import { ApiError } from './apiError'
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
    body: {
      email: 'user@example.com',
      password: 'Password123!',
    },
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/login',
    expect.objectContaining({
      credentials: 'include',
      method: 'POST',
    }),
  )
  const init = fetchMock.mock.calls[0][1] as RequestInit
  const headers = new Headers(init.headers)
  expect(headers.get('content-type')).toBe('application/json')
  expect(headers.get('x-csrf-token')).toBe('csrf-123')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('csrf_token cookie がない unsafe request では csrf を 1 回 bootstrap する', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    if (input === '/api/auth/csrf') {
      document.cookie = 'csrf_token=csrf-bootstrapped; path=/'
      return Promise.resolve(new Response(null, { status: 204 }))
    }

    return Promise.resolve(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/auth/login', {
    body: {
      email: 'user@example.com',
      password: 'Password123!',
    },
  })

  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/auth/csrf', {
    credentials: 'include',
  })
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    '/api/auth/login',
    expect.objectContaining({
      method: 'POST',
    }),
  )
  const init = fetchMock.mock.calls[1][1] as RequestInit
  const headers = new Headers(init.headers)
  expect(headers.get('x-csrf-token')).toBe('csrf-bootstrapped')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('CSRF_VALIDATION_FAILED の 403 は csrf 再取得後に 1 回だけ retry する', async () => {
  document.cookie = 'csrf_token=stale-token; path=/'
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: 'CSRF_VALIDATION_FAILED',
              message: 'CSRF validation failed',
            },
          }),
          {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          },
        ),
      ),
    )
    .mockImplementationOnce(() => {
      document.cookie = 'csrf_token=fresh-token; path=/'
      return Promise.resolve(new Response(null, { status: 204 }))
    })
    .mockImplementationOnce(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/auth/login', {
    body: {
      email: 'user@example.com',
      password: 'Password123!',
    },
  })

  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/auth/login',
    expect.objectContaining({
      method: 'POST',
    }),
  )
  const firstInit = fetchMock.mock.calls[0][1] as RequestInit
  expect(new Headers(firstInit.headers).get('x-csrf-token')).toBe('stale-token')
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/auth/csrf', {
    credentials: 'include',
  })
  expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    '/api/auth/login',
    expect.objectContaining({
      method: 'POST',
    }),
  )
  const retryInit = fetchMock.mock.calls[2][1] as RequestInit
  expect(new Headers(retryInit.headers).get('x-csrf-token')).toBe('fresh-token')
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('古い csrf bootstrap の完了は強制再取得中の bootstrap を解除しない', async () => {
  let resolveFirstBootstrap: (response: Response) => void = () => {}
  let resolveForcedBootstrap: (response: Response) => void = () => {}
  const firstBootstrap = new Promise<Response>((resolve) => {
    resolveFirstBootstrap = resolve
  })
  const forcedBootstrap = new Promise<Response>((resolve) => {
    resolveForcedBootstrap = resolve
  })
  let csrfRequestCount = 0
  let retryRequestCount = 0
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    if (input === '/api/auth/csrf') {
      csrfRequestCount += 1
      if (csrfRequestCount === 1) {
        return firstBootstrap
      }
      if (csrfRequestCount === 2) {
        return forcedBootstrap
      }

      document.cookie = 'csrf_token=unexpected-token; path=/'
      return Promise.resolve(new Response(null, { status: 204 }))
    }

    if (input === '/api/retry') {
      retryRequestCount += 1
      if (retryRequestCount === 1) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: {
                code: 'CSRF_VALIDATION_FAILED',
                message: 'CSRF validation failed',
              },
            }),
            {
              status: 403,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
        )
      }
    }

    return Promise.resolve(new Response(null, { status: 204 }))
  })
  vi.stubGlobal('fetch', fetchMock)

  const firstRequest = apiClient.post('/api/first')
  await vi.waitFor(() => expect(csrfRequestCount).toBe(1))

  document.cookie = 'csrf_token=stale-token; path=/'
  const retryingRequest = apiClient.post('/api/retry')
  await vi.waitFor(() => expect(csrfRequestCount).toBe(2))

  resolveFirstBootstrap(new Response(null, { status: 204 }))
  await firstRequest
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'

  const joiningRequest = apiClient.post('/api/join')
  await Promise.resolve()

  document.cookie = 'csrf_token=fresh-token; path=/'
  resolveForcedBootstrap(new Response(null, { status: 204 }))
  await Promise.all([retryingRequest, joiningRequest])

  expect(csrfRequestCount).toBe(2)
})

test('CSRF retry 後も 403 の場合は ApiError を投げる', async () => {
  document.cookie = 'csrf_token=stale-token; path=/'
  const csrfFailureBody = {
    error: {
      code: 'CSRF_VALIDATION_FAILED',
      message: 'CSRF validation failed',
    },
  }
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify(csrfFailureBody), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    .mockImplementationOnce(() => {
      document.cookie = 'csrf_token=fresh-token; path=/'
      return Promise.resolve(new Response(null, { status: 204 }))
    })
    .mockResolvedValueOnce(
      new Response(JSON.stringify(csrfFailureBody), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  vi.stubGlobal('fetch', fetchMock)

  await expect(apiClient.post('/api/auth/login', { body: {} })).rejects.toEqual(
    expect.objectContaining({
      status: 403,
      code: 'CSRF_VALIDATION_FAILED',
    }),
  )
  expect(fetchMock).toHaveBeenCalledTimes(3)
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
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'CSRF unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await expect(
    apiClient.post('/api/auth/login', {
      body: {
        email: 'user@example.com',
        password: 'Password123!',
      },
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

test.each([
  ['PUT', () => apiClient.put('/api/resource', { body: { name: 'updated' } })],
  [
    'PATCH',
    () => apiClient.patch('/api/resource', { body: { name: 'patched' } }),
  ],
  ['DELETE', () => apiClient.delete('/api/resource')],
])('%s request を送信できる', async (method, request) => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await request()

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/resource',
    expect.objectContaining({ method }),
  )
})

test('AbortSignal を fetch に渡す', async () => {
  const controller = new AbortController()
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await apiClient.get('/api/auth/me', { signal: controller.signal })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/me',
    expect.objectContaining({ signal: controller.signal }),
  )
})

test.each([
  ['false', false],
  ['0', 0],
  ['empty string', ''],
])('%s の body を送信できる', async (_label, body) => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/falsy', { body })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/falsy',
    expect.objectContaining({
      body: JSON.stringify(body),
    }),
  )
})

test('呼び出し側 headers を保ったまま csrf header を追加する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/headers', {
    body: { ok: true },
    headers: {
      Accept: 'application/json',
      'X-Request-ID': 'request-1',
    },
  })

  const init = fetchMock.mock.calls[0][1] as RequestInit
  const headers = new Headers(init.headers)

  expect(headers.get('accept')).toBe('application/json')
  expect(headers.get('x-request-id')).toBe('request-1')
  expect(headers.get('x-csrf-token')).toBe('csrf-123')
})

test('ApiError 以外の 403 は CSRF retry しない', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Forbidden' }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await expect(
    apiClient.post('/api/forbidden', { body: {} }),
  ).rejects.toBeInstanceOf(ApiError)
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
