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

test('register 成功後は redirect 先へ遷移し auth cache を同期する', async () => {
  document.cookie = 'csrf_token=csrf-token; Path=/'
  const user = authUser()
  let registered = false
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        if (registered) {
          return Promise.resolve(jsonResponse(user, 200))
        }

        return Promise.resolve(jsonResponse({ detail: 'Unauthorized' }, 401))
      }

      registered = true
      return Promise.resolve(jsonResponse(user, 201))
    }),
  )

  const { router, queryClient } = renderWithRouter({
    initialEntries: ['/ja/register?redirect=/app%3Ftab%3Dsettings'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  await submitRegisterForm()
  await screen.findByRole('heading', { name: 'アプリ' })

  expect(router.state.location.href).toBe('/app?tab=settings')
  expect(queryClient.getQueryData(queryKeys.auth.me)).toEqual(user)
})

test('EMAIL_ALREADY_REGISTERED は専用メッセージを表示する', async () => {
  setupRegisterError(409, {
    error: {
      code: 'EMAIL_ALREADY_REGISTERED',
      message: 'Email already registered',
    },
  })

  renderWithRouter({
    initialEntries: ['/ja/register'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  await submitRegisterForm()

  expect((await screen.findByRole('alert')).textContent).toBe(
    'このメールアドレスはすでに登録されています。ログインしてください。',
  )
})

test('VALIDATION_ERROR は入力確認メッセージを表示する', async () => {
  setupRegisterError(422, {
    error: {
      code: 'VALIDATION_ERROR',
      message: 'Validation error',
    },
  })

  renderWithRouter({
    initialEntries: ['/ja/register'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  await submitRegisterForm()

  expect((await screen.findByRole('alert')).textContent).toBe(
    '入力内容を確認してください。',
  )
})

test('REGISTER_RATE_LIMITED は rate limit メッセージを表示する', async () => {
  setupRegisterError(429, {
    error: {
      code: 'REGISTER_RATE_LIMITED',
      message: 'Too many register attempts',
    },
  })

  renderWithRouter({
    initialEntries: ['/ja/register'],
    queryClientOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  await submitRegisterForm()

  expect((await screen.findByRole('alert')).textContent).toBe(
    '登録試行回数が多すぎます。時間をおいて再度お試しください。',
  )
})

test('register は OIDC provider button を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/oidc/providers') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              providers: [{ providerId: 'google', displayName: 'Google' }],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        )
      }

      return Promise.resolve(jsonResponse({ detail: 'Unauthorized' }, 401))
    }),
  )

  renderWithRouter({
    initialEntries: ['/ja/register?redirect=/app%3Ftab%3Dsettings'],
  })

  expect(
    await screen.findByRole('button', { name: 'Googleで続行' }),
  ).toBeTruthy()
})

test('ログイン済みユーザーが /register を開くと redirect 先へ送られる', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation(() => Promise.resolve(jsonResponse(authUser(), 200))),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/ja/register?redirect=/app%3Ftab%3Dsettings'],
  })

  await screen.findByRole('heading', { name: 'アプリ' })

  expect(router.state.location.href).toBe('/app?tab=settings')
})

test('legacy /register は path/search を保って locale 付き URL へ正規化する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(jsonResponse({ detail: 'Unauthorized' }, 401)),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/register?redirect=%2Fapp%3Ftab%3Dsettings'],
  })

  await screen.findByRole('heading', { name: '新規登録' })

  expect(router.state.location.pathname).toBe('/ja/register')
  expect(router.state.location.search.redirect).toBe('/app?tab=settings')
})

test('legacy /register は hash を保って locale 付き URL へ正規化する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(jsonResponse({ detail: 'Unauthorized' }, 401)),
  )

  const { router } = renderWithRouter({
    initialEntries: ['/register#form'],
  })

  await screen.findByRole('heading', { name: '新規登録' })

  expect(router.state.location.pathname).toBe('/ja/register')
  expect(router.state.location.hash).toBe('form')
})

async function submitRegisterForm() {
  fireEvent.change(await screen.findByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.change(screen.getByLabelText('パスワード確認'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを作成' }))
}

function setupRegisterError(status: number, body: unknown) {
  document.cookie = 'csrf_token=csrf-token; Path=/'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        return Promise.resolve(jsonResponse({ detail: 'Unauthorized' }, 401))
      }

      return Promise.resolve(jsonResponse(body, status))
    }),
  )
}

function authUser() {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    roles: [],
    permissions: [],
  }
}

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
