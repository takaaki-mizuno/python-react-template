// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'
import { describe, expect, test, vi } from 'vitest'

import { routeTree } from '@/routeTree.gen'
import {
  finalSection,
  heroContent,
  landingNavigation,
  landingSectionIds,
  sectionHeadingIds,
} from '@/routes/index.data'

vi.mock('@tanstack/react-devtools', () => ({
  TanStackDevtools: () => null,
}))

vi.mock('@tanstack/react-router-devtools', () => ({
  TanStackRouterDevtoolsPanel: () => null,
}))

describe('LandingPage route', () => {
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
    const queryClient = new QueryClient()
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({
        initialEntries: ['/'],
      }),
      context: { queryClient },
    })

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )

    await screen.findByText('FastAPI と React を、すぐ動かせる実用的なモノレポ')

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

    for (const item of landingNavigation) {
      expect(container.querySelector(`a[href="${item.href}"]`)).not.toBeNull()
    }

    for (const action of heroContent.actions) {
      expect(
        screen.getByRole('link', { name: action.label }).getAttribute('href'),
      ).toBe(action.href)
    }

    for (const action of finalSection.actions) {
      expect(
        screen.getByRole('link', { name: action.label }).getAttribute('href'),
      ).toBe(action.href)
    }
  })
})
