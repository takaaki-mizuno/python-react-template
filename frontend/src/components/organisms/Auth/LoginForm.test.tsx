// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import LoginForm from './LoginForm'

test('LoginForm は email / password を submit する', () => {
  const onSubmit = vi.fn(() => Promise.resolve())

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
