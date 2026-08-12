// @vitest-environment jsdom

import { cleanup, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { landingSectionIds, sectionHeadingIds } from './data'
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

describe('LandingPage route', () => {
  test('legacy / は search/hash を保って locale 付き URL へ正規化する', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: 'Unauthorized' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    const { router } = renderWithRouter({
      initialEntries: ['/?ref=docs#quality'],
    })

    await screen.findByText('FastAPI と React を、すぐ動かせる実用的なモノレポ')

    expect(router.state.location.pathname).toBe('/ja')
    expect(router.state.location.searchStr).toBe('?ref=docs')
    expect(router.state.location.hash).toBe('quality')
  })

  test('トップページに主要セクションとアンカー CTA を表示する', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: 'Unauthorized' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const { container } = renderWithRouter()

    await screen.findByText('FastAPI と React を、すぐ動かせる実用的なモノレポ')
    expect(
      screen.getByRole('complementary', { name: 'このテンプレートの要点' }),
    ).toBeTruthy()

    for (const sectionId of landingSectionIds) {
      const section = container.querySelector<HTMLElement>(
        `section#${sectionId}`,
      )

      expect(section).not.toBeNull()
      expect(section?.getAttribute('aria-labelledby')).toBe(
        sectionHeadingIds[sectionId],
      )
      expect(
        container.querySelector<HTMLElement>(
          `#${sectionHeadingIds[sectionId]}`,
        ),
      ).not.toBeNull()
    }

    for (const sectionId of landingSectionIds) {
      expect(container.querySelector(`a[href="#${sectionId}"]`)).not.toBeNull()
    }

    for (const action of [
      { href: '#architecture', label: '構成を見る' },
      { href: '#workflow', label: '進め方を見る' },
    ]) {
      expect(
        screen.getByRole('link', { name: action.label }).getAttribute('href'),
      ).toBe(action.href)
    }

    for (const action of [
      { href: '#overview', label: '概要に戻る' },
      { href: '#quality', label: '品質を見る' },
    ]) {
      expect(
        screen.getByRole('link', { name: action.label }).getAttribute('href'),
      ).toBe(action.href)
    }
  })
})
