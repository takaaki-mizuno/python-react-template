// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import RegisterForm from './RegisterForm'

afterEach(() => {
  cleanup()
})

test('RegisterForm は email / password を submit する', () => {
  const onSubmit = vi.fn()

  render(
    <RegisterForm errorMessage={null} isPending={false} onSubmit={onSubmit} />,
  )

  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.change(screen.getByLabelText('パスワード確認'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを作成' }))

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'user@example.com',
    password: 'Password123!',
  })
})

test('RegisterForm の password input は new-password autocomplete を持つ', () => {
  render(
    <RegisterForm errorMessage={null} isPending={false} onSubmit={vi.fn()} />,
  )

  expect(screen.getByLabelText('パスワード').getAttribute('autocomplete')).toBe(
    'new-password',
  )
  expect(
    screen.getByLabelText('パスワード確認').getAttribute('autocomplete'),
  ).toBe('new-password')
})

test('RegisterForm は confirmation 不一致なら submit せず alert を表示する', () => {
  const onSubmit = vi.fn()

  render(
    <RegisterForm errorMessage={null} isPending={false} onSubmit={onSubmit} />,
  )

  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.change(screen.getByLabelText('パスワード確認'), {
    target: { value: 'Different123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'アカウントを作成' }))

  expect(onSubmit).not.toHaveBeenCalled()
  expect(screen.getByRole('alert').textContent).toBe(
    'パスワードが一致しません。',
  )
  expect(
    screen.getByLabelText('メールアドレス').getAttribute('aria-invalid'),
  ).toBeNull()
  expect(screen.getByLabelText('パスワード').getAttribute('aria-invalid')).toBe(
    'true',
  )
  expect(
    screen.getByLabelText('パスワード確認').getAttribute('aria-invalid'),
  ).toBe('true')
})

test('RegisterForm は pending 中に submit button を disabled にする', () => {
  render(<RegisterForm errorMessage={null} isPending onSubmit={vi.fn()} />)

  expect(
    screen
      .getByRole('button', { name: 'アカウントを作成' })
      .hasAttribute('disabled'),
  ).toBe(true)
})

test('RegisterForm は backend error message を alert で表示する', () => {
  render(
    <RegisterForm
      errorMessage="このメールアドレスはすでに登録されています。ログインしてください。"
      isPending={false}
      onSubmit={vi.fn()}
    />,
  )

  expect(screen.getByRole('alert').textContent).toBe(
    'このメールアドレスはすでに登録されています。ログインしてください。',
  )
})
