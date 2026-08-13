// @vitest-environment jsdom

import { cleanup, fireEvent, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

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
          new Response(JSON.stringify({ csrf_token: 'csrf-token' }), {
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
  renderWithRouter({
    initialEntries: ['/ja/login'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

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

test('login 成功後は正規化済み redirect 先へ遷移し auth cache を同期する', async () => {
  document.cookie = 'csrf_token=csrf-token; Path=/'
  const user = {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    roles: ['admin'],
    permissions: ['admin:access'],
  }
  let loginSucceeded = false
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        if (loginSucceeded) {
          return Promise.resolve(
            new Response(JSON.stringify(user), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
          )
        }
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Unauthorized' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      if (input === '/api/auth/csrf') {
        return Promise.resolve(
          new Response(JSON.stringify({ csrf_token: 'csrf-token' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      loginSucceeded = true
      return Promise.resolve(
        new Response(JSON.stringify(user), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )

  const { router, queryClient } = renderWithRouter({
    initialEntries: ['/ja/login?redirect=/app%3Ftab%3Dsettings'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  fireEvent.change(await screen.findByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))

  await screen.findByRole('heading', { name: 'アプリ' })

  expect(router.state.location.href).toBe('/app?tab=settings')
  expect(queryClient.getQueryData(queryKeys.auth.me)).toEqual(user)
})

test('危険な redirect は /app へ正規化する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/ja/login?redirect=https%3A%2F%2Fevil.example%2Fapp'],
  })

  await screen.findByRole('heading', { name: 'ログイン' })

  expect(router.state.location.search.redirect).toBe('/app')
})

test('legacy /login は path/search を保って locale 付き URL へ正規化する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/login?redirect=%2Fapp%3Ftab%3Dsettings'],
  })

  await screen.findByRole('heading', { name: 'ログイン' })

  expect(router.state.location.pathname).toBe('/ja/login')
  expect(router.state.location.search.redirect).toBe('/app?tab=settings')
})

test('legacy /login は hash を保って locale 付き URL へ正規化する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/login#form'],
  })

  await screen.findByRole('heading', { name: 'ログイン' })

  expect(router.state.location.pathname).toBe('/ja/login')
  expect(router.state.location.hash).toBe('form')
})

test('login は redirect を引き継いだ register link を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({
    initialEntries: ['/ja/login?redirect=/app%3Ftab%3Dsettings'],
  })

  expect(
    (
      await screen.findByRole('link', { name: 'アカウントを作成' })
    ).getAttribute('href'),
  ).toBe('/ja/register?redirect=%2Fapp%3Ftab%3Dsettings')
})

test('login は OIDC provider button を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/oidc/providers') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              data: [{ provider_id: 'google', display_name: 'Google' }],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        )
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: 'Unauthorized' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )

  renderWithRouter({
    initialEntries: ['/ja/login?redirect=/app%3Ftab%3Dsettings'],
  })

  expect(
    await screen.findByRole('button', { name: 'Googleで続行' }),
  ).toBeTruthy()
})

test('login は OIDC callback error を form-level message にする', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({
    initialEntries: ['/ja/login?oidc_error=OIDC_IDENTITY_LINK_REQUIRED'],
  })

  expect((await screen.findByRole('alert')).textContent).toBe(
    '既存アカウントでログインしてから連携してください。',
  )
})

test.each([
  [
    'OIDC_AUTHORIZATION_RATE_LIMITED',
    '認証リクエストが多すぎます。時間をおいて再度お試しください。',
  ],
  [
    'OIDC_PROVIDER_UNAVAILABLE',
    '認証プロバイダーに接続できませんでした。時間をおいて再度お試しください。',
  ],
  [
    'OIDC_PROVIDER_METADATA_INVALID',
    '認証プロバイダー設定に問題があります。管理者に連絡してください。',
  ],
  [
    'OIDC_PROVIDER_ACCESS_DENIED',
    '認証プロバイダーでログインがキャンセルされました。',
  ],
  [
    'OIDC_IDENTITY_UNAVAILABLE',
    'このアカウントは現在利用できません。管理者に連絡してください。',
  ],
  [
    'OIDC_REAUTH_AUTHENTICATION_REQUIRED',
    '再認証のセッションが切れました。もう一度ログインしてください。',
  ],
])('login は OIDC error %s を専用メッセージにする', async (code, message) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({
    initialEntries: [`/ja/login?oidc_error=${code}`],
  })

  expect((await screen.findByRole('alert')).textContent).toBe(message)
})

test('ログイン済みユーザーが /login を開くと redirect 先へ送られる', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() =>
      Promise.resolve(
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
      ),
    ),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/ja/login?redirect=/app%3Ftab%3Dsettings'],
  })

  await screen.findByRole('heading', { name: 'アプリ' })

  expect(router.state.location.href).toBe('/app?tab=settings')
})
