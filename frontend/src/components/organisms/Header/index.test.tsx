// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { routeTree } from '@/routeTree.gen'
import { landingNavigation } from '@/routes/index.data'

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

function renderWithRouter(initialEntries: Array<string> = ['/']) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  const queryClient = new QueryClient()
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries }),
    context: { queryClient },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('Header', () => {
  test('メニューの開閉とリンク押下での close を制御する', async () => {
    const { container } = renderWithRouter()
    const desktopNav = await screen.findByRole('navigation', {
      name: 'ページ内ナビゲーション',
    })

    for (const item of landingNavigation) {
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
    renderWithRouter()

    const menuButton = await screen.findByRole('button', {
      name: 'メニューを開く',
    })

    fireEvent.click(menuButton)
    expect(menuButton.getAttribute('aria-expanded')).toBe('true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(menuButton.getAttribute('aria-expanded')).toBe('false')
  })

  test('未ログイン時はログイン導線を表示する', async () => {
    renderWithRouter()

    expect(
      (await screen.findByRole('link', { name: 'ログイン' })).getAttribute(
        'href',
      ),
    ).toBe('/login?redirect=%2Fapp')
  })
})
