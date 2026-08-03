// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import AuthMenu from './AuthMenu'
import type { ReactNode } from 'react'

const navigateMock = vi.fn()
const logoutMutateAsyncMock = vi.fn()

let currentUser: { email: string } | null = null
let logoutIsPending = false

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    search,
    to,
    ...props
  }: {
    children: ReactNode
    search?: { redirect?: string }
    to: string
  }) => {
    const redirect = search?.redirect
      ? `?redirect=${encodeURIComponent(search.redirect)}`
      : ''

    return (
      <a href={`${to}${redirect}`} {...props}>
        {children}
      </a>
    )
  },
  useNavigate: () => navigateMock,
}))

vi.mock('@/hooks/useAuthSession', () => ({
  useAuthSession: () => ({
    logout: {
      isPending: logoutIsPending,
      mutateAsync: logoutMutateAsyncMock,
    },
    user: currentUser,
  }),
}))

afterEach(() => {
  cleanup()
  currentUser = null
  logoutIsPending = false
  navigateMock.mockReset()
  logoutMutateAsyncMock.mockReset()
})

describe('AuthMenu', () => {
  test('未ログイン時はログインと新規登録の導線を表示する', () => {
    render(<AuthMenu />)

    expect(
      screen.getByRole('link', { name: 'ログイン' }).getAttribute('href'),
    ).toBe('/login?redirect=%2Fapp')
    expect(
      screen.getByRole('link', { name: '新規登録' }).getAttribute('href'),
    ).toBe('/register?redirect=%2Fapp')
  })

  test('ログイン済み時は email と logout button を表示する', () => {
    currentUser = { email: 'user@example.com' }

    render(<AuthMenu />)

    expect(screen.getByText('user@example.com')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'ログアウト' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'ログイン' })).toBeNull()
  })

  test('ログアウト成功時は login へ遷移する', async () => {
    currentUser = { email: 'user@example.com' }
    logoutMutateAsyncMock.mockResolvedValue(undefined)

    render(<AuthMenu />)

    fireEvent.click(screen.getByRole('button', { name: 'ログアウト' }))

    await waitFor(() => {
      expect(logoutMutateAsyncMock).toHaveBeenCalledOnce()
      expect(navigateMock).toHaveBeenCalledWith({
        search: { redirect: '/app' },
        to: '/login',
      })
    })
  })

  test('ログアウト失敗時は alert を表示する', async () => {
    currentUser = { email: 'user@example.com' }
    logoutMutateAsyncMock.mockRejectedValue(new Error('logout failed'))

    render(<AuthMenu />)

    fireEvent.click(screen.getByRole('button', { name: 'ログアウト' }))

    expect((await screen.findByRole('alert')).textContent).toBe(
      'ログアウトに失敗しました。時間をおいて再度お試しください。',
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
