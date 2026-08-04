// @vitest-environment jsdom

import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
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
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('/app/settings で account deletion に成功すると cache を消して / へ遷移する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  let accountDeleted = false
  const fetchMock = vi
    .fn()
    .mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        accountDeleted = true
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (input === '/api/auth/me' && accountDeleted) {
        return Promise.resolve(new Response(null, { status: 401 }))
      }

      return Promise.resolve(authUserResponse())
    })
  vi.stubGlobal('fetch', fetchMock)
  const { router, queryClient } = renderWithRouter({
    initialEntries: ['/app/settings'],
    seed: (client) => {
      client.setQueryData(['projects'], [{ id: 'project-1' }])
    },
  })

  expect(
    await screen.findByRole('heading', { name: 'アカウント削除' }),
  ).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'アカウント設定' })).toBeTruthy()
  expect(
    screen.getByRole('link', { name: 'アプリに戻る' }).getAttribute('href'),
  ).toBe('/app')
  fireEvent.change(
    screen.getByLabelText('メールアドレスを入力して削除を確認'),
    {
      target: { value: 'user@example.com' },
    },
  )
  fireEvent.change(screen.getByLabelText('現在のパスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  await waitFor(() => expect(router.state.location.pathname).toBe('/'))
  const deleteCall = fetchMock.mock.calls.find(
    ([input, init]) => input === '/api/auth/me' && init?.method === 'DELETE',
  )
  expect(deleteCall?.[1]?.body).toBe(
    JSON.stringify({
      confirmEmail: 'user@example.com',
      password: 'Password123!',
    }),
  )
  expect(queryClient.getQueryData(['projects'])).toBeUndefined()
})

test.each([
  [
    400,
    'ACCOUNT_DELETION_CONFIRMATION_MISMATCH',
    '入力されたメールアドレスが現在のアカウントと一致しません。',
    'confirmEmail',
  ],
  [
    400,
    'ACCOUNT_DELETION_REAUTH_REQUIRED',
    'アカウント削除には現在のパスワード入力が必要です。',
    'password',
  ],
  [
    400,
    'ACCOUNT_DELETION_INVALID_PASSWORD',
    '現在のパスワードが一致しません。',
    'password',
  ],
  [
    429,
    'ACCOUNT_DELETION_REAUTH_RATE_LIMITED',
    '確認の試行回数が多すぎます。時間をおいて再度お試しください。',
    null,
  ],
  [
    403,
    'CSRF_VALIDATION_FAILED',
    'セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。',
    null,
  ],
])(
  '/app/settings は account deletion API error %s %s を表示する',
  async (status, code, message, invalidField) => {
    document.cookie = 'csrf_token=csrf-123; path=/'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: string, init?: RequestInit) => {
        if (input === '/api/auth/me' && init?.method === 'DELETE') {
          return Promise.resolve(apiErrorResponse(status, code))
        }

        return Promise.resolve(authUserResponse())
      }),
    )

    renderWithRouter({ initialEntries: ['/app/settings'] })

    expect(
      await screen.findByRole('heading', { name: 'アカウント削除' }),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

    expect((await screen.findByRole('alert')).textContent).toBe(message)
    expect(
      screen
        .getByLabelText('メールアドレスを入力して削除を確認')
        .getAttribute('aria-invalid'),
    ).toBe(invalidField === 'confirmEmail' ? 'true' : null)
    expect(
      screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
    ).toBe(invalidField === 'password' ? 'true' : null)
  },
)

test('/app/settings は空の confirmEmail 由来の 422 を入力確認 message にする', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: [{ msg: 'Invalid email' }] }), {
            status: 422,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }

      return Promise.resolve(authUserResponse())
    }),
  )

  renderWithRouter({ initialEntries: ['/app/settings'] })

  expect(
    await screen.findByRole('heading', { name: 'アカウント削除' }),
  ).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  expect((await screen.findByRole('alert')).textContent).toBe(
    '入力内容を確認してください。',
  )
})

test('/app/settings は非 ApiError で fallback message を表示する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.reject(new Error('network down'))
      }

      return Promise.resolve(authUserResponse())
    }),
  )

  renderWithRouter({ initialEntries: ['/app/settings'] })

  expect(
    await screen.findByRole('heading', { name: 'アカウント削除' }),
  ).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  expect((await screen.findByRole('alert')).textContent).toBe(
    'アカウント削除に失敗しました。時間をおいて再度お試しください。',
  )
})

test('/app には settings への導線がある', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  renderWithRouter({ initialEntries: ['/app'] })

  expect(
    (await screen.findByRole('link', { name: 'アカウント設定' })).getAttribute(
      'href',
    ),
  ).toBe('/app/settings')
})

function authUserResponse() {
  return new Response(
    JSON.stringify({
      id: '00000000-0000-0000-0000-000000000001',
      email: 'user@example.com',
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    },
  )
}

function apiErrorResponse(status: number, code: string) {
  return new Response(
    JSON.stringify({
      error: {
        code,
        message: code,
      },
    }),
    {
      status,
      headers: { 'Content-Type': 'application/json' },
    },
  )
}
