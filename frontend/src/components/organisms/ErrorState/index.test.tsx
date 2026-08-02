// @vitest-environment jsdom

import { cleanup, screen } from '@testing-library/react'
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

test('ErrorState は status / title / message / primary action を表示する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  renderWithRouter({ initialEntries: ['/missing'] })

  expect(await screen.findByText('404')).toBeTruthy()
  expect(
    screen.getByRole('heading', { name: 'ページが見つかりません' }),
  ).toBeTruthy()
  expect(
    screen.getByText(
      '指定されたページは存在しないか、移動した可能性があります。',
    ),
  ).toBeTruthy()
  expect(
    screen.getByRole('link', { name: 'トップへ戻る' }).getAttribute('href'),
  ).toBe('/')
})
