// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import HeaderNav from './HeaderNav'

const items = [
  { href: '#overview', label: '概要' },
  { href: '#quality', label: '品質' },
] as const

afterEach(() => {
  cleanup()
})

test('HeaderNav は desktop navigation items を表示する', () => {
  render(<HeaderNav items={items} />)

  expect(
    screen.getByRole('navigation', { name: 'ページ内ナビゲーション' }),
  ).toBeTruthy()
  expect(screen.getByRole('link', { name: '概要' }).getAttribute('href')).toBe(
    '#overview',
  )
})

test('HeaderNav は mobile navigation click で onNavigate を呼ぶ', () => {
  const onNavigate = vi.fn()
  render(<HeaderNav items={items} mobile onNavigate={onNavigate} />)

  fireEvent.click(screen.getByRole('link', { name: '品質' }))

  expect(onNavigate).toHaveBeenCalledOnce()
})
