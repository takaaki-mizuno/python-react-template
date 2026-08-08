// @vitest-environment jsdom

import { useMutation } from '@tanstack/react-query'
import { createMemoryHistory } from '@tanstack/react-router'
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/apiError'
import { createAppRouter } from '@/lib/appRouter'
import { queryKeys } from '@/lib/queryKeys'
import { renderWithRouter } from '@/test/renderRouter'

vi.mock('@tanstack/react-devtools', () => ({
  TanStackDevtools: () => null,
}))

vi.mock('@tanstack/react-router-devtools', () => ({
  TanStackRouterDevtoolsPanel: () => null,
}))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('未ログインで /app へ来たら /login へ送る', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({ initialEntries: ['/app'] })

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()
})

test('logout 後は cached user を使わず /me を再確認する', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  renderWithRouter({
    initialEntries: ['/app'],
    seed: (queryClient) => {
      queryClient.setQueryData(queryKeys.auth.me, {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'user@example.com',
        roles: [],
        permissions: [],
      })
    },
  })

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/me',
    expect.objectContaining({ credentials: 'include' }),
  )
})

test('/app の 5xx は未ログイン扱いで redirect しない', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const { router } = createAppRouter({
    history: createMemoryHistory({ initialEntries: ['/app'] }),
    queryClientOptions: { queries: { retry: false } },
  })

  await router.load()

  expect(router.state.location.pathname).toBe('/app')
  expect(router.state.matches.some((match) => match.status === 'error')).toBe(
    true,
  )
  renderWithRouter({
    initialEntries: ['/app'],
    queryClientOptions: { queries: { retry: false } },
  })
  expect(
    await screen.findByRole('heading', { name: '問題が発生しました' }),
  ).toBeTruthy()
  expect(screen.queryByText('Internal Server Error')).toBeNull()
})

test('Header は guard 直後の auth.me cache があれば /me を二重取得しない', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        id: '00000000-0000-0000-0000-000000000001',
        email: 'user@example.com',
        roles: [],
        permissions: [],
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      },
    ),
  )
  vi.stubGlobal('fetch', fetchMock)

  const { router } = renderWithRouter({ initialEntries: ['/app'] })

  expect(await screen.findByRole('heading', { name: 'アプリ' })).toBeTruthy()
  await waitFor(() => expect(router.state.status).toBe('idle'))
  await act(async () => {})
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('/app 表示後に query が 401 になると /login へ遷移し auth cache を null にする', async () => {
  let sessionExpired = false
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => {
      if (sessionExpired) {
        return Promise.resolve(unauthorizedResponse())
      }

      return Promise.resolve(authUserResponse())
    }),
  )

  const { router, queryClient } = renderWithRouter({ initialEntries: ['/app'] })

  expect(await screen.findByRole('heading', { name: 'アプリ' })).toBeTruthy()
  queryClient.setQueryData(queryKeys.auth.me, {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    roles: [],
    permissions: [],
  })

  await queryClient
    .fetchQuery({
      queryKey: ['session-expired'],
      queryFn: () => {
        sessionExpired = true
        return Promise.reject(new ApiError(401, null))
      },
    })
    .catch(() => undefined)

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login')
  })
  expect(router.state.location.search.redirect).toBe('/app')
  expect(queryClient.getQueryData(queryKeys.auth.me)).toBeNull()
})

test('/login 表示中の 401 は redirect loop しない', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const { router, queryClient } = renderWithRouter({
    initialEntries: ['/login'],
  })

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()

  await queryClient
    .fetchQuery({
      queryKey: ['login-401'],
      queryFn: () => Promise.reject(new ApiError(401, null)),
    })
    .catch(() => undefined)

  expect(router.state.location.pathname).toBe('/login')
})

test('CSRF 403 は /forbidden へ遷移しない', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  const { router, queryClient } = renderWithRouter({ initialEntries: ['/app'] })

  expect(await screen.findByRole('heading', { name: 'アプリ' })).toBeTruthy()

  await queryClient
    .fetchQuery({
      queryKey: ['csrf-403'],
      queryFn: () =>
        Promise.reject(
          new ApiError(403, {
            error: {
              code: 'CSRF_VALIDATION_FAILED',
              message: 'CSRF validation failed',
            },
          }),
        ),
    })
    .catch(() => undefined)

  expect(router.state.location.pathname).toBe('/app')
})

test('CSRF 以外の 403 は /forbidden へ遷移する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  const { router, queryClient } = renderWithRouter({ initialEntries: ['/app'] })

  expect(await screen.findByRole('heading', { name: 'アプリ' })).toBeTruthy()

  await queryClient
    .fetchQuery({
      queryKey: ['forbidden-403'],
      queryFn: () =>
        Promise.reject(
          new ApiError(403, {
            error: { code: 'FORBIDDEN', message: 'Forbidden' },
          }),
        ),
    })
    .catch(() => undefined)

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/forbidden')
  })
})

test('/admin は admin:access permission があれば表示する', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    authUserResponse({
      roles: ['admin'],
      permissions: ['admin:access'],
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  renderWithRouter({ initialEntries: ['/admin'] })

  expect(await screen.findByRole('heading', { name: '管理' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('/admin は admin:access permission がなければ /forbidden へ遷移する', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authUserResponse()))

  renderWithRouter({ initialEntries: ['/admin'] })

  expect(
    await screen.findByRole('heading', { name: 'アクセスできません' }),
  ).toBeTruthy()
})

test('mutation の CSRF 以外の 403 は /forbidden へ遷移する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/app'],
    children: <ForbiddenMutationButton />,
  })

  expect(await screen.findByRole('heading', { name: 'アプリ' })).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'mutation 403' }))

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/forbidden')
  })
})

test('未定義 route は 404 ErrorState を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({ initialEntries: ['/missing'] })

  expect(
    await screen.findByRole('heading', { name: 'ページが見つかりません' }),
  ).toBeTruthy()
  expect(screen.getByText('404')).toBeTruthy()
})

test('/forbidden は 403 ErrorState を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({ initialEntries: ['/forbidden'] })

  expect(
    await screen.findByRole('heading', { name: 'アクセスできません' }),
  ).toBeTruthy()
  expect(screen.getByText('403')).toBeTruthy()
})

function ForbiddenMutationButton() {
  const mutation = useMutation({
    mutationFn: () =>
      Promise.reject(
        new ApiError(403, {
          error: {
            code: 'PERMISSION_DENIED',
            message: 'Permission denied',
          },
        }),
      ),
  })

  return (
    <button type="button" onClick={() => mutation.mutate()}>
      mutation 403
    </button>
  )
}

function authUserResponse(overrides?: {
  roles?: Array<string>
  permissions?: Array<string>
}) {
  return new Response(
    JSON.stringify({
      id: '00000000-0000-0000-0000-000000000001',
      email: 'user@example.com',
      roles: overrides?.roles ?? [],
      permissions: overrides?.permissions ?? [],
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    },
  )
}

function unauthorizedResponse() {
  return new Response(JSON.stringify({ detail: 'Unauthorized' }), {
    status: 401,
    headers: { 'Content-Type': 'application/json' },
  })
}
