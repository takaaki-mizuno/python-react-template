// @vitest-environment jsdom

import { isRedirect } from '@tanstack/react-router'
import { afterEach, describe, expect, test, vi } from 'vitest'

import {
  requireAnyPermission,
  requireAuth,
  requirePermission,
} from './authGuard'
import { createTestQueryClient } from '@/test/queryClient'

describe('authGuard', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('requireAuth 後の requirePermission は current user を二重 fetch しない', async () => {
    const queryClient = createTestQueryClient()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          email: 'admin@example.com',
          roles: ['admin'],
          permissions: ['admin:access'],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await requireAuth({
      context: { queryClient },
      location: { href: '/app/admin' },
    })
    await requirePermission('admin:access', {
      context: { queryClient },
      location: { href: '/app/admin' },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  test('requirePermission は未認証 user を login redirect にする', async () => {
    const queryClient = createTestQueryClient()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    )

    try {
      await requirePermission('admin:access', {
        context: { queryClient },
        location: { href: '/app/admin' },
      })
      throw new Error('requirePermission should redirect')
    } catch (error) {
      expect(isRedirect(error)).toBe(true)
      const redirectError = error as RedirectError
      expect(redirectError.options).toMatchObject({
        to: '/login',
        search: { redirect: '/app/admin' },
      })
    }
  })

  test('requireAnyPermission は権限がなければ forbidden redirect にする', async () => {
    const queryClient = createTestQueryClient()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: '00000000-0000-0000-0000-000000000002',
            email: 'user@example.com',
            roles: [],
            permissions: ['users:read'],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    try {
      await requireAnyPermission(['admin:access', 'users:write'], {
        context: { queryClient },
        location: { href: '/app/admin' },
      })
      throw new Error('requireAnyPermission should redirect')
    } catch (error) {
      expect(isRedirect(error)).toBe(true)
      const redirectError = error as RedirectError
      expect(redirectError.options).toMatchObject({ to: '/forbidden' })
    }
  })

  test('requirePermission は current user fetch の 5xx を redirect に変換しない', async () => {
    const queryClient = createTestQueryClient()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'UNEXPECTED' } }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(
      requirePermission('admin:access', {
        context: { queryClient },
        location: { href: '/app/admin' },
      }),
    ).rejects.toMatchObject({ status: 500 })
  })
})

type RedirectError = {
  options: {
    to: string
    search?: { redirect: string }
  }
}
