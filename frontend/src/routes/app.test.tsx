// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { queryKeys } from '@/lib/queryKeys'
import { routeTree } from '@/routeTree.gen'

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
  const queryClient = new QueryClient()
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/app'] }),
    context: { queryClient },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()
})

test('logout 後は cached user を使わず /me を再確認する', async () => {
  const queryClient = new QueryClient()
  queryClient.setQueryData(queryKeys.auth.strictMe, {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
  })
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/app'] }),
    context: { queryClient },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/me',
    expect.objectContaining({ credentials: 'include' }),
  )
})

test('/app の 5xx は未ログイン扱いで redirect しない', async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/app'] }),
    context: { queryClient },
  })

  await router.load()

  expect(router.state.location.pathname).toBe('/app')
  expect(router.state.matches.at(-1)?.status).toBe('error')
})
