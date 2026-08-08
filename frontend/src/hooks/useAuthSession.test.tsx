// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { useAuthSession } from './useAuthSession'
import type { ReactNode } from 'react'
import { queryKeys } from '@/lib/queryKeys'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('401 は未ログインとして null を返す', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient()

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.user).toBeNull())
})

test('500 は未ログインに潰さず error として残す', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Server error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient()

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.error).toBeTruthy())
})

test('logout 成功時は表示中userを null にして auth 以外の cache も消す', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const user = {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    roles: [],
    permissions: [],
  }
  let loggedOut = false
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) => {
      if (input === '/api/auth/me') {
        if (loggedOut) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'Unauthorized' }), {
              status: 401,
              headers: { 'Content-Type': 'application/json' },
            }),
          )
        }

        return Promise.resolve(
          new Response(JSON.stringify(user), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      if (input === '/api/auth/csrf') {
        return Promise.resolve(
          new Response(JSON.stringify({ csrfToken: 'csrf-123' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
      loggedOut = true
      return Promise.resolve(new Response(null, { status: 204 }))
    }),
  )
  const queryClient = new QueryClient()
  queryClient.setQueryData(['projects'], [{ id: 'project-1' }])
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useAuthSession(), { wrapper })
  await waitFor(() => expect(result.current.user).toEqual(user))

  await act(async () => {
    await result.current.logout.mutateAsync()
  })

  await waitFor(() => expect(result.current.user).toBeNull())
  expect(queryClient.getQueryData(queryKeys.auth.me)).toBeNull()
  expect(queryClient.getQueryData(['projects'])).toBeUndefined()
})

test('未ログイン状態から auth cache が更新されると user を返す', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.user).toBeNull())

  const nextUser = {
    id: '00000000-0000-0000-0000-000000000002',
    email: 'next@example.com',
    roles: [],
    permissions: [],
  }

  act(() => {
    queryClient.setQueryData(queryKeys.auth.me, nextUser)
  })

  await waitFor(() => expect(result.current.user).toEqual(nextUser))
})
