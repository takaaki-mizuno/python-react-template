// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AccountDeletionPanel } from './AccountDeletionPanel'

afterEach(() => {
  cleanup()
})

test('現在の email と確認入力欄を表示し、空や不一致でも submit button は有効にする', () => {
  render(
    <AccountDeletionPanel currentEmail="user@example.com" onSubmit={vi.fn()} />,
  )

  const confirmEmail =
    screen.getByLabelText('メールアドレスを入力して削除を確認')
  const password = screen.getByLabelText('現在のパスワード')
  const submitButton = screen.getByRole('button', {
    name: 'アカウントを削除',
  })

  expect(screen.getByText('user@example.com')).toBeTruthy()
  expect(password.getAttribute('type')).toBe('password')
  expect(confirmEmail.getAttribute('autocomplete')).toBe('off')
  expect(password.getAttribute('autocomplete')).toBe('current-password')
  expect(confirmEmail.hasAttribute('required')).toBe(false)
  expect(password.hasAttribute('required')).toBe(false)
  expect(submitButton.hasAttribute('disabled')).toBe(false)
})

test('pending 中は入力欄と submit button を disabled にする', () => {
  render(
    <AccountDeletionPanel
      currentEmail="user@example.com"
      isPending
      onSubmit={vi.fn()}
    />,
  )

  expect(
    screen
      .getByLabelText('メールアドレスを入力して削除を確認')
      .hasAttribute('disabled'),
  ).toBe(true)
  expect(
    screen.getByLabelText('現在のパスワード').hasAttribute('disabled'),
  ).toBe(true)
  expect(
    screen
      .getByRole('button', { name: 'アカウントを削除' })
      .hasAttribute('disabled'),
  ).toBe(true)
})

test('入力値を submit し、空 password は undefined にする', () => {
  const onSubmit = vi.fn()
  render(
    <AccountDeletionPanel
      currentEmail="user@example.com"
      onSubmit={onSubmit}
    />,
  )

  fireEvent.change(
    screen.getByLabelText('メールアドレスを入力して削除を確認'),
    {
      target: { value: 'user@example.com' },
    },
  )
  fireEvent.change(screen.getByLabelText('現在のパスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  expect(onSubmit).toHaveBeenCalledWith({
    confirmEmail: 'user@example.com',
    password: 'Password123!',
  })

  onSubmit.mockClear()
  fireEvent.change(screen.getByLabelText('現在のパスワード'), {
    target: { value: '' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを削除' }))

  expect(onSubmit).toHaveBeenCalledWith({
    confirmEmail: 'user@example.com',
    password: undefined,
  })
})

test('error message は alert として表示し、指定された field だけ invalid にする', () => {
  render(
    <AccountDeletionPanel
      currentEmail="user@example.com"
      errorMessage="現在のパスワードが一致しません。"
      invalidField="password"
      onSubmit={vi.fn()}
    />,
  )

  expect(screen.getByRole('alert').textContent).toBe(
    '現在のパスワードが一致しません。',
  )
  expect(
    screen
      .getByLabelText('メールアドレスを入力して削除を確認')
      .getAttribute('aria-invalid'),
  ).toBeNull()
  expect(
    screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
  ).toBe('true')
})

test('field に紐づかない error message では input を invalid にしない', () => {
  render(
    <AccountDeletionPanel
      currentEmail="user@example.com"
      errorMessage="確認の試行回数が多すぎます。時間をおいて再度お試しください。"
      onSubmit={vi.fn()}
    />,
  )

  expect(
    screen
      .getByLabelText('メールアドレスを入力して削除を確認')
      .getAttribute('aria-invalid'),
  ).toBeNull()
  expect(
    screen.getByLabelText('現在のパスワード').getAttribute('aria-invalid'),
  ).toBeNull()
})
