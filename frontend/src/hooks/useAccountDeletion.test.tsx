// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { useAccountDeletion } from './useAccountDeletion'
import type { ReactNode } from 'react'
import {
  readLastResolvedLanguage,
  writeLastResolvedLanguage,
} from '@/lib/i18n/storage'
import { queryKeys } from '@/lib/queryKeys'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('account deletion 成功時は logout と同じ cache policy を適用する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient()
  writeLastResolvedLanguage('en')
  queryClient.setQueryData(queryKeys.auth.me, {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'user@example.com',
    languageCode: 'en',
    roles: [],
    permissions: [],
  })
  queryClient.setQueryData(['projects'], [{ id: 'project-1' }])
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAccountDeletion(), { wrapper })

  await act(async () => {
    await result.current.mutateAsync({
      confirmEmail: 'user@example.com',
      password: 'Password123!',
    })
  })

  expect(queryClient.getQueryData(queryKeys.auth.me)).toBeNull()
  expect(queryClient.getQueryData(['projects'])).toBeUndefined()
  expect(readLastResolvedLanguage()).toBeNull()
})
