// @vitest-environment jsdom

import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { LanguageCode } from '@/lib/i18n/languages'
import { writePublicLanguage } from '@/lib/i18n/storage'
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
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('未認証で /app/settings を開くと login へ redirect する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          type: '/problems/unauthorized',
          title: 'Unauthorized',
          status: 401,
          detail: 'Unauthorized',
          code: 'unauthorized',
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ),
  )

  const { router } = renderWithRouter({ initialEntries: ['/app/settings'] })

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/ja/login')
  })
  expect(router.state.location.search.redirect).toBe('/app/settings')
  expect(screen.queryByRole('heading', { name: 'アカウント設定' })).toBeNull()
})

test('/app/settings で account deletion に成功すると cache を消して public fallback locale の / へ遷移する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  writePublicLanguage('ja')
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

      return Promise.resolve(
        authUserResponse({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'user@example.com',
          language_code: 'en',
        }),
      )
    })
  vi.stubGlobal('fetch', fetchMock)
  const { router, queryClient } = renderWithRouter({
    initialEntries: ['/app/settings'],
    seed: (client) => {
      client.setQueryData(['projects'], [{ id: 'project-1' }])
    },
  })

  expect(
    await screen.findByRole('heading', { name: 'Delete account' }),
  ).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Account settings' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'App' }).getAttribute('href')).toBe(
    '/app',
  )
  fireEvent.change(
    screen.getByLabelText('Enter your email address to confirm deletion'),
    {
      target: { value: 'user@example.com' },
    },
  )
  fireEvent.change(screen.getByLabelText('Current password'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))

  await waitFor(() => expect(router.state.location.pathname).toBe('/ja'))
  const deleteCall = fetchMock.mock.calls.find(
    ([input, init]) => input === '/api/auth/me' && init?.method === 'DELETE',
  )
  expect(deleteCall?.[1]?.body).toBe(
    JSON.stringify({
      confirm_email: 'user@example.com',
      password: 'Password123!',
    }),
  )
  expect(queryClient.getQueryData(['projects'])).toBeUndefined()
})

test.each([
  [
    400,
    'account_deletion_confirmation_mismatch',
    '入力されたメールアドレスが現在のアカウントと一致しません。',
    'confirm_email',
  ],
  [
    400,
    'account_deletion_reauth_required',
    'アカウント削除には現在のパスワード入力が必要です。',
    'password',
  ],
  [
    400,
    'account_deletion_invalid_password',
    '現在のパスワードが一致しません。',
    'password',
  ],
  [
    429,
    'account_deletion_reauth_rate_limited',
    '確認の試行回数が多すぎます。時間をおいて再度お試しください。',
    null,
  ],
  [
    403,
    'csrf_validation_failed',
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

    const authUser = {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'user@example.com',
      roles: [],
      permissions: [],
    }
    const { queryClient } = renderWithRouter({
      initialEntries: ['/app/settings'],
      seed: (client) => {
        client.setQueryData(queryKeys.auth.me, authUser)
        client.setQueryData(['projects'], [{ id: 'project-1' }])
      },
    })

    expect(
      await screen.findByRole('heading', { name: 'アカウント削除' }),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

    expect((await screen.findByRole('alert')).textContent).toBe(message)
    expect(
      screen
        .getByLabelText('メールアドレスを入力して削除を確認')
        .getAttribute('aria-invalid'),
    ).toBe(invalidField === 'confirm_email' ? 'true' : null)
    expect(
      screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
    ).toBe(invalidField === 'password' ? 'true' : null)
    expect(queryClient.getQueryData(queryKeys.auth.me)).toEqual(authUser)
    expect(queryClient.getQueryData(['projects'])).toEqual([
      { id: 'project-1' },
    ])
  },
)

test('/app/settings は Retry-After 付き account deletion 429 を retry-aware message にする', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          apiErrorResponse(429, 'account_deletion_reauth_rate_limited', {
            'Retry-After': '900',
          }),
        )
      }

      return Promise.resolve(authUserResponse())
    }),
  )

  const authUser = {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    roles: [],
    permissions: [],
  }
  const { queryClient } = renderWithRouter({
    initialEntries: ['/app/settings'],
    seed: (client) => {
      client.setQueryData(queryKeys.auth.me, authUser)
      client.setQueryData(['projects'], [{ id: 'project-1' }])
    },
  })

  expect(
    await screen.findByRole('heading', { name: 'アカウント削除' }),
  ).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  expect((await screen.findByRole('alert')).textContent).toBe(
    '確認の試行回数が多すぎます。15分後に再度お試しください。',
  )
  expect(
    screen
      .getByLabelText('メールアドレスを入力して削除を確認')
      .getAttribute('aria-invalid'),
  ).toBeNull()
  expect(
    screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
  ).toBeNull()
  expect(queryClient.getQueryData(queryKeys.auth.me)).toEqual(authUser)
  expect(queryClient.getQueryData(['projects'])).toEqual([{ id: 'project-1' }])
})

test('/app/settings は OIDC reauth required details から reauth button を表示する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          apiErrorResponse(
            400,
            'account_deletion_oidc_reauth_required',
            {},
            {
              providers: [{ provider_id: 'google', display_name: 'Google' }],
            },
          ),
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
    'アカウント削除にはOAuth/OIDC再認証が必要です。',
  )
  expect(screen.getByRole('button', { name: 'Googleで続行' })).toBeTruthy()
  expect(
    screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
  ).toBeNull()
})

test('/app/settings は linked providers が空なら reauth button を出さない', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          apiErrorResponse(
            400,
            'account_deletion_oidc_reauth_required',
            {},
            { providers: [] },
          ),
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
    '再認証できる連携プロバイダーがありません。サポートに連絡してください。',
  )
  expect(screen.queryByRole('button', { name: 'Googleで続行' })).toBeNull()
})

test('/app/settings は OIDC reauth callback result query を message にする', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  renderWithRouter({
    initialEntries: ['/app/settings?oidc_error=OIDC_REAUTH_STALE'],
  })

  expect((await screen.findByRole('alert')).textContent).toBe(
    '再認証の有効期限が切れています。もう一度お試しください。',
  )
})

test.each([
  [
    'OIDC_PROVIDER_ACCESS_DENIED',
    '認証プロバイダーで再認証がキャンセルされました。',
  ],
  [
    'OIDC_PROVIDER_UNAVAILABLE',
    '認証プロバイダーに接続できませんでした。時間をおいて再度お試しください。',
  ],
  [
    'OIDC_IDENTITY_UNAVAILABLE',
    'この連携アカウントは現在利用できません。管理者に連絡してください。',
  ],
])(
  '/app/settings は OIDC reauth error %s を専用 message にする',
  async (code, message) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
    )

    renderWithRouter({
      initialEntries: [`/app/settings?oidc_error=${code}`],
    })

    expect((await screen.findByRole('alert')).textContent).toBe(message)
  },
)

test('/app/settings は OIDC reauth success query を message にする', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  renderWithRouter({
    initialEntries: ['/app/settings?oidc_reauth=success'],
  })

  expect((await screen.findByRole('alert')).textContent).toBe(
    '再認証が完了しました。もう一度アカウント削除を実行してください。',
  )
})

test('/app/settings はフォーム編集後に OIDC query message を再表示しない', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Promise.resolve(authUserResponse())),
  )

  renderWithRouter({
    initialEntries: ['/app/settings?oidc_reauth=success'],
  })

  expect((await screen.findByRole('alert')).textContent).toBe(
    '再認証が完了しました。もう一度アカウント削除を実行してください。',
  )
  fireEvent.change(
    screen.getByLabelText('メールアドレスを入力して削除を確認'),
    {
      target: { value: 'user@example.com' },
    },
  )

  expect(screen.queryByRole('alert')).toBeNull()
})

test('/app/settings は OIDC reauth 後の full-page load で最新 user を読む', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }

      return Promise.resolve(
        authUserResponse({
          id: '00000000-0000-0000-0000-000000000002',
          email: 'fresh@example.com',
        }),
      )
    })
  vi.stubGlobal('fetch', fetchMock)

  renderWithRouter({
    initialEntries: ['/app/settings?oidc_reauth=success'],
  })

  expect(
    await screen.findByRole('heading', { name: 'アカウント削除' }),
  ).toBeTruthy()
  fireEvent.change(
    screen.getByLabelText('メールアドレスを入力して削除を確認'),
    {
      target: { value: 'fresh@example.com' },
    },
  )
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({
          confirm_email: 'fresh@example.com',
        }),
      }),
    )
  })
})

test('/app/settings は空の confirm_email 由来の 422 を field-specific message にする', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              type: '/problems/validation_error',
              title: 'Validation error',
              status: 422,
              detail: 'Request validation failed.',
              code: 'validation_error',
              errors: [
                {
                  location: 'body',
                  pointer: '#/confirm_email',
                  detail: 'Field required',
                  code: 'missing',
                },
              ],
            }),
            {
              status: 422,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
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
    'メールアドレスを入力してください。',
  )
  expect(
    screen
      .getByLabelText('メールアドレスを入力して削除を確認')
      .getAttribute('aria-invalid'),
  ).toBe('true')
})

test('/app/settings は invalid field 編集時に stale field error を消す', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          apiErrorResponse(400, 'account_deletion_invalid_password'),
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
    '現在のパスワードが一致しません。',
  )
  fireEvent.change(
    screen.getByLabelText('メールアドレスを入力して削除を確認'),
    {
      target: { value: 'user@example.com' },
    },
  )
  expect(screen.queryByRole('alert')).toBeTruthy()

  fireEvent.change(screen.getByLabelText('現在のパスワード'), {
    target: { value: 'Password123!' },
  })
  expect(screen.queryByRole('alert')).toBeNull()
  expect(
    screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
  ).toBeNull()
})

test('/app/settings は form-level error を field 編集で消さない', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      if (input === '/api/auth/me' && init?.method === 'DELETE') {
        return Promise.resolve(
          apiErrorResponse(429, 'account_deletion_reauth_rate_limited'),
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
    '確認の試行回数が多すぎます。時間をおいて再度お試しください。',
  )
  fireEvent.change(screen.getByLabelText('現在のパスワード'), {
    target: { value: 'Password123!' },
  })

  expect(screen.queryByRole('alert')).toBeTruthy()
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

function authUserResponse(
  user: {
    email: string
    id: string
    language_code?: LanguageCode
  } = {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
  },
) {
  return new Response(
    JSON.stringify({
      roles: [],
      permissions: [],
      ...user,
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    },
  )
}

function apiErrorResponse(
  status: number,
  code: string,
  headers?: Record<string, string>,
  extensions: Record<string, unknown> = {},
) {
  return new Response(
    JSON.stringify({
      type: `/problems/${code}`,
      title: code,
      status,
      detail: code,
      code,
      ...extensions,
    }),
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', ...headers },
    },
  )
}
