// @vitest-environment jsdom

import { cleanup, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

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

test('/admin/users は admin:access がなければ forbidden へ送る', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authUserResponse([])))

  const { router } = renderWithRouter({ initialEntries: ['/admin/users'] })

  await waitFor(() => expect(router.state.location.pathname).toBe('/forbidden'))
})

test('/admin/users は検索 query を一覧 API に反映する', async () => {
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    if (input === '/api/auth/me') {
      return Promise.resolve(authUserResponse(['admin:access']))
    }
    if (input === '/api/admin/roles') {
      return Promise.resolve(jsonResponse({ roles: [], permissions: [] }))
    }
    if (input.startsWith('/api/admin/users')) {
      return Promise.resolve(
        jsonResponse({ data: [], count: 0, offset: 20, limit: 20 }),
      )
    }
    return Promise.resolve(jsonResponse({}))
  })
  vi.stubGlobal('fetch', fetchMock)

  renderWithRouter({
    initialEntries: ['/admin/users?offset=20&query=admin&is_active=false'],
  })

  expect(
    await screen.findByRole('heading', { name: 'ユーザー管理' }),
  ).toBeTruthy()
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes(
          '/api/admin/users?offset=20&limit=20&query=admin&is_active=false',
        ),
      ),
    ).toBe(true),
  )
})

function authUserResponse(permissions: Array<string>) {
  return jsonResponse({
    id: 'user-1',
    email: 'admin@example.com',
    roles: permissions.length ? ['admin'] : [],
    permissions,
  })
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}
