// @vitest-environment jsdom

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import Header from './index'
import type { ReactNode } from 'react'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('./AuthMenu', () => ({
  default: () => <div data-testid="auth-menu" />,
}))

const navigationItems = [
  { href: '#overview', label: '概要' },
  { href: '#quality', label: '品質' },
] as const

afterEach(() => {
  cleanup()
})

describe('Header structure', () => {
  test('navigationItems を渡さない場合は landing navigation と mobile menu button を表示しない', () => {
    render(<Header />)

    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.queryByRole('button', { name: 'メニューを開く' })).toBeNull()
    expect(screen.getByTestId('auth-menu')).toBeTruthy()
  })

  test('navigationItems を渡した場合だけ navigation と mobile menu を表示する', () => {
    render(<Header navigationItems={navigationItems} />)

    expect(
      screen.getByRole('navigation', { name: 'ページ内ナビゲーション' }),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'メニューを開く' })).toBeTruthy()
  })

  test('mobile navigation のリンク押下で panel を閉じる', () => {
    const { container } = render(<Header navigationItems={navigationItems} />)
    const menuButton = screen.getByRole('button', { name: 'メニューを開く' })

    fireEvent.click(menuButton)

    const controlsId = menuButton.getAttribute('aria-controls') as string
    const panel = container.querySelector(`#${controlsId}`) as HTMLElement

    fireEvent.click(screen.getAllByRole('link', { name: '品質' })[1])

    expect(panel.hidden).toBe(true)
  })

  test('Header は route-specific data を import しない', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/components/organisms/Header/index.tsx'),
      'utf-8',
    )

    expect(source).not.toContain('routes/index.data')
    expect(source).not.toContain('@/routes/')
  })
})
