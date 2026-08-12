// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
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
    params,
    search,
    to,
    ...props
  }: {
    children: ReactNode
    params?: { locale?: string }
    search?: { redirect?: string }
    to: string
  }) => {
    const pathname = params?.locale
      ? to.replace('/{-$locale}', `/${params.locale}`)
      : to
    const redirect = search?.redirect
      ? `?redirect=${encodeURIComponent(search.redirect)}`
      : ''

    return (
      <a href={`${pathname}${redirect}`} {...props}>
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

function openAccountMenu(trigger: HTMLElement) {
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
}

describe('AuthMenu', () => {
  test('未ログイン時はログインと新規登録の導線を表示する', () => {
    render(<AuthMenu />)

    expect(
      screen.getByRole('link', { name: 'ログイン' }).getAttribute('href'),
    ).toBe('/ja/login?redirect=%2Fapp')
    expect(
      screen.getByRole('link', { name: '新規登録' }).getAttribute('href'),
    ).toBe('/ja/register?redirect=%2Fapp')
  })

  test('ログイン済み時は email と logout button を表示する', () => {
    currentUser = { email: 'user@example.com' }

    render(<AuthMenu />)

    const accountTrigger = screen.getByRole('button', {
      name: 'user@example.com アカウントメニュー',
    })

    expect(within(accountTrigger).getByText('user@example.com')).toBeTruthy()
    openAccountMenu(accountTrigger)
    expect(screen.getByRole('menuitem', { name: 'ログアウト' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'ログイン' })).toBeNull()
  })

  test('ログアウト成功時は login へ遷移する', async () => {
    currentUser = { email: 'user@example.com' }
    logoutMutateAsyncMock.mockResolvedValue(undefined)

    render(<AuthMenu />)

    const accountTrigger = screen.getByRole('button', {
      name: 'user@example.com アカウントメニュー',
    })
    openAccountMenu(accountTrigger)
    fireEvent.click(screen.getByRole('menuitem', { name: 'ログアウト' }))

    await waitFor(() => {
      expect(logoutMutateAsyncMock).toHaveBeenCalledOnce()
      expect(navigateMock).toHaveBeenCalledWith({
        href: '/ja/login?redirect=/app',
      })
    })
  })

  test('ログアウト失敗時は alert を表示する', async () => {
    currentUser = { email: 'user@example.com' }
    logoutMutateAsyncMock.mockRejectedValue(new Error('logout failed'))

    render(<AuthMenu />)

    const accountTrigger = screen.getByRole('button', {
      name: 'user@example.com アカウントメニュー',
    })
    openAccountMenu(accountTrigger)
    fireEvent.click(screen.getByRole('menuitem', { name: 'ログアウト' }))

    expect((await screen.findByRole('alert')).textContent).toBe(
      'ログアウトに失敗しました。時間をおいて再度お試しください。',
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'ログアウトエラーを閉じる' }),
    )
    expect(screen.queryByRole('alert')).toBeNull()
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
