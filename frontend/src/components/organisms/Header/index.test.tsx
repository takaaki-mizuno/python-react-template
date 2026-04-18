// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import Header from '.'
import { landingNavigation } from '@/routes/index.data'

afterEach(() => {
  cleanup()
})

describe('Header', () => {
  test('メニューの開閉とリンク押下での close を制御する', () => {
    const { container } = render(<Header />)
    const desktopNav = screen.getByRole('navigation', {
      name: 'ページ内ナビゲーション',
    })

    for (const item of landingNavigation) {
      expect(
        within(desktopNav)
          .getByRole('link', { name: item.label })
          .getAttribute('href'),
      ).toBe(item.href)
    }

    const menuButton = screen.getByRole('button', { name: 'メニューを開く' })

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

  test('Escape キー押下でメニューを閉じる', () => {
    render(<Header />)

    const menuButton = screen.getByRole('button', { name: 'メニューを開く' })

    fireEvent.click(menuButton)
    expect(menuButton.getAttribute('aria-expanded')).toBe('true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(menuButton.getAttribute('aria-expanded')).toBe('false')
  })
})
