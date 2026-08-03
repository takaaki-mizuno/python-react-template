// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { renderWithRouter } from '@/test/renderRouter'

vi.mock('@tanstack/react-devtools', () => ({
  TanStackDevtools: () => null,
}))

vi.mock('@tanstack/react-router-devtools', () => ({
  TanStackRouterDevtoolsPanel: () => null,
}))

const headerNavigation = [
  { href: '#overview', label: '概要' },
  { href: '#architecture', label: '構成' },
  { href: '#workflow', label: '進め方' },
  { href: '#quality', label: '品質' },
] as const

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

function renderHeaderRoute(initialEntries: Array<string> = ['/']) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  return renderWithRouter({ initialEntries })
}

describe('Header', () => {
  test('メニューの開閉とリンク押下での close を制御する', async () => {
    const { container } = renderHeaderRoute()
    const desktopNav = await screen.findByRole('navigation', {
      name: 'ページ内ナビゲーション',
    })

    for (const item of headerNavigation) {
      expect(
        within(desktopNav)
          .getByRole('link', { name: item.label })
          .getAttribute('href'),
      ).toBe(item.href)
    }

    const menuButton = await screen.findByRole('button', {
      name: 'メニューを開く',
    })

    expect(menuButton.getAttribute('aria-expanded')).toBe('false')

    const controlsId = menuButton.getAttribute('aria-controls')

    expect(controlsId).toBeTruthy()

    fireEvent.click(menuButton)
    expect(menuButton.getAttribute('aria-expanded')).toBe('true')

    const mobileNav = within(
      container.querySelector(`#${controlsId}`) as HTMLElement,
    ).getByRole('navigation', { name: 'モバイルページ内ナビゲーション' })
    const qualityLink = within(mobileNav).getByRole('link', { name: '品質' })

    expect(qualityLink.getAttribute('href')).toBe('#quality')

    fireEvent.click(qualityLink)
    expect(menuButton.getAttribute('aria-expanded')).toBe('false')
  })

  test('Escape キー押下でメニューを閉じる', async () => {
    renderHeaderRoute()

    const menuButton = await screen.findByRole('button', {
      name: 'メニューを開く',
    })

    fireEvent.click(menuButton)
    expect(menuButton.getAttribute('aria-expanded')).toBe('true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(menuButton.getAttribute('aria-expanded')).toBe('false')
  })

  test('未ログイン時はログイン導線を表示する', async () => {
    renderHeaderRoute()

    expect(
      (await screen.findByRole('link', { name: 'ログイン' })).getAttribute(
        'href',
      ),
    ).toBe('/login?redirect=%2Fapp')
    expect(
      (await screen.findByRole('link', { name: '新規登録' })).getAttribute(
        'href',
      ),
    ).toBe('/register?redirect=%2Fapp')
  })

  test('ログイン済み時は email と logout button を表示し、login/register link は出さない', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authUserResponse()))

    renderWithRouter()

    expect(await screen.findByText('user@example.com')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'ログアウト' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'ログイン' })).toBeNull()
    expect(screen.queryByRole('link', { name: '新規登録' })).toBeNull()
  })

  test('ログアウト失敗時は alert を表示し、現在画面に留まる', async () => {
    document.cookie = 'csrf_token=csrf-123; path=/'
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        return Promise.resolve(authUserResponse())
      }

      return Promise.resolve(
        new Response(JSON.stringify({ detail: 'Server error' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    const { router } = renderWithRouter({ initialEntries: ['/app'] })

    fireEvent.click(await screen.findByRole('button', { name: 'ログアウト' }))

    expect((await screen.findByRole('alert')).textContent).toBe(
      'ログアウトに失敗しました。時間をおいて再度お試しください。',
    )
    expect(router.state.location.pathname).toBe('/app')
  })

  test('ログアウト処理中はボタンを disabled にする', async () => {
    document.cookie = 'csrf_token=csrf-123; path=/'
    let resolveLogout: (response: Response) => void = () => {}
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: string) => {
        if (input === '/api/auth/me') {
          return Promise.resolve(authUserResponse())
        }

        return logoutResponse
      }),
    )

    const { router } = renderWithRouter({ initialEntries: ['/app'] })
    const logoutButton = await screen.findByRole('button', {
      name: 'ログアウト',
    })

    fireEvent.click(logoutButton)

    await waitFor(() =>
      expect(logoutButton.hasAttribute('disabled')).toBe(true),
    )

    resolveLogout(new Response(null, { status: 204 }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login')
    })
  })

  test('ログアウト後に再ログインすると新しい user を表示する', async () => {
    document.cookie = 'csrf_token=csrf-123; path=/'
    const firstUser = {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'user@example.com',
    }
    const nextUser = {
      id: '00000000-0000-0000-0000-000000000002',
      email: 'next@example.com',
    }
    let session: 'first' | 'none' | 'next' = 'first'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: string) => {
        if (input === '/api/auth/me') {
          if (session === 'first') {
            return Promise.resolve(jsonResponse(firstUser))
          }
          if (session === 'next') {
            return Promise.resolve(jsonResponse(nextUser))
          }

          return Promise.resolve(jsonResponse({ detail: 'Unauthorized' }, 401))
        }

        if (input === '/api/auth/logout') {
          session = 'none'
          return Promise.resolve(new Response(null, { status: 204 }))
        }

        if (input === '/api/auth/login') {
          session = 'next'
          return Promise.resolve(jsonResponse(nextUser))
        }

        return Promise.resolve(new Response(null, { status: 204 }))
      }),
    )

    const { router } = renderWithRouter({ initialEntries: ['/app'] })

    expect(await screen.findByText(firstUser.email)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'ログアウト' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))

    fireEvent.change(await screen.findByLabelText('メールアドレス'), {
      target: { value: nextUser.email },
    })
    fireEvent.change(screen.getByLabelText('パスワード'), {
      target: { value: 'Password123!' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
    expect(await screen.findByText(nextUser.email)).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'ログイン' })).toBeNull()
  })
})

function authUserResponse() {
  return jsonResponse({
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
  })
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
