// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { routeTree } from '@/routeTree.gen'

vi.mock('@tanstack/react-devtools', () => ({
  TanStackDevtools: () => null,
}))

vi.mock('@tanstack/react-router-devtools', () => ({
  TanStackRouterDevtoolsPanel: () => null,
}))

afterEach(() => {
  cleanup()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.unstubAllGlobals()
})

test('login の 5xx を画面上のエラーとして表示する', async () => {
  document.cookie = 'csrf_token=csrf-token; Path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Unauthorized' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      if (input === '/api/auth/csrf') {
        return Promise.resolve(
          new Response(JSON.stringify({ csrfToken: 'csrf-token' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/login'] }),
    context: { queryClient },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )

  fireEvent.change(await screen.findByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))

  expect((await screen.findByRole('alert')).textContent).toBe(
    'ログインに失敗しました。時間をおいて再度お試しください。',
  )
})
