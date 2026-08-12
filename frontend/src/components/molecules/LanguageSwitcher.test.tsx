// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { LanguageSwitcher } from './LanguageSwitcher'

afterEach(() => {
  cleanup()
})

function openLanguageMenu() {
  fireEvent.pointerDown(
    screen.getByRole('button', { name: '表示言語を変更' }),
    {
      button: 0,
      ctrlKey: false,
    },
  )
}

test('LanguageSwitcher は現在言語と選択肢を表示し、変更を通知する', async () => {
  const onChangeLanguage = vi.fn()
  render(
    <LanguageSwitcher
      currentLanguage="ja"
      onChangeLanguage={onChangeLanguage}
    />,
  )

  openLanguageMenu()

  const menu = await screen.findByRole('menu')
  const japaneseItem = within(menu).getByRole('menuitemradio', {
    name: '日本語',
  })
  const englishItem = within(menu).getByRole('menuitemradio', {
    name: 'English',
  })

  expect(japaneseItem.getAttribute('aria-checked')).toBe('true')
  fireEvent.click(englishItem)
  expect(onChangeLanguage).toHaveBeenCalledWith('en')
})

test('LanguageSwitcher は pending 中に操作を抑止する', () => {
  render(
    <LanguageSwitcher
      currentLanguage="ja"
      isPending
      onChangeLanguage={vi.fn()}
    />,
  )

  const trigger = screen.getByRole('button', { name: '表示言語を変更' })
  expect(trigger.getAttribute('disabled')).toBeNull()
  expect(trigger.getAttribute('aria-busy')).toBe('true')

  openLanguageMenu()

  const menu = screen.getByRole('menu')
  expect(
    within(menu)
      .getByRole('menuitemradio', { name: 'English' })
      .getAttribute('aria-disabled'),
  ).toBe('true')
  expect(
    within(menu)
      .getByRole('menuitemradio', { name: '日本語' })
      .getAttribute('aria-disabled'),
  ).toBe('true')
})

test('LanguageSwitcher は menu 内にエラー文言を表示しない', () => {
  render(<LanguageSwitcher currentLanguage="ja" onChangeLanguage={vi.fn()} />)

  openLanguageMenu()

  expect(screen.queryByText('言語設定を保存できませんでした。')).toBeNull()
})
