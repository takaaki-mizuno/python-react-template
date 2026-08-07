// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { AuthFormFeedback } from './AuthFormFeedback'

test('message が null の場合は alert を描画しない', () => {
  render(<AuthFormFeedback id="auth-error" message={null} />)

  expect(screen.queryByRole('alert')).toBeNull()
})

test('message がある場合は指定 id の alert として描画する', () => {
  render(
    <AuthFormFeedback id="auth-error" message="入力内容を確認してください。" />,
  )

  const alert = screen.getByRole('alert')
  expect(alert.id).toBe('auth-error')
  expect(alert.textContent).toBe('入力内容を確認してください。')
})
