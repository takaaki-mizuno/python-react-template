// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import LoginForm from './LoginForm'

afterEach(() => {
  cleanup()
})

test('LoginForm は email / password を submit する', () => {
  const onSubmit = vi.fn()

  render(
    <LoginForm errorMessage={null} isPending={false} onSubmit={onSubmit} />,
  )

  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'user@example.com',
    password: 'Password123!',
  })
})

test('LoginForm は入力欄の autocomplete を設定する', () => {
  render(<LoginForm errorMessage={null} isPending={false} onSubmit={vi.fn()} />)

  expect(
    screen.getByLabelText('メールアドレス').getAttribute('autocomplete'),
  ).toBe('email')
  expect(screen.getByLabelText('パスワード').getAttribute('autocomplete')).toBe(
    'current-password',
  )
})

test('LoginForm はエラー表示時に入力欄へ説明を紐付ける', () => {
  render(
    <LoginForm
      errorMessage="メールアドレスまたはパスワードが正しくありません。"
      isPending={false}
      onSubmit={vi.fn()}
    />,
  )

  const alert = screen.getByRole('alert')
  const email = screen.getByLabelText('メールアドレス')
  const password = screen.getByLabelText('パスワード')

  expect(email.getAttribute('aria-invalid')).toBeNull()
  expect(password.getAttribute('aria-invalid')).toBeNull()
  expect(email.getAttribute('aria-describedby')).toBe(alert.id)
  expect(password.getAttribute('aria-describedby')).toBe(alert.id)
})

test('LoginForm は pending 中に submit button を disabled にする', () => {
  render(<LoginForm errorMessage={null} isPending onSubmit={vi.fn()} />)

  expect(
    screen.getByRole('button', { name: 'ログイン' }).hasAttribute('disabled'),
  ).toBe(true)
})
