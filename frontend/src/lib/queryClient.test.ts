// @vitest-environment jsdom

import { describe, expect, test, vi } from 'vitest'

import { ApiError } from './apiError'
import { createAppQueryClient } from './queryClient'

describe('createAppQueryClient', () => {
  test('query が 401 で失敗すると onUnauthorized を呼ぶ', async () => {
    const onUnauthorized = vi.fn()
    const queryClient = createAppQueryClient({ onUnauthorized })

    await expect(
      queryClient.fetchQuery({
        queryKey: ['requires-auth'],
        queryFn: () => Promise.reject(new ApiError(401, null)),
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  test('mutation が 401 で失敗すると onUnauthorized を呼ぶ', async () => {
    const onUnauthorized = vi.fn()
    const queryClient = createAppQueryClient({ onUnauthorized })

    await expect(
      queryClient
        .getMutationCache()
        .build(queryClient, {
          mutationFn: () => Promise.reject(new ApiError(401, null)),
        })
        .execute(undefined),
    ).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  test('CSRF 以外の 403 で onForbidden を呼ぶ', async () => {
    const onForbidden = vi.fn()
    const queryClient = createAppQueryClient({ onForbidden })
    const error = new ApiError(403, {
      error: { code: 'FORBIDDEN', message: 'Forbidden' },
    })

    await expect(
      queryClient.fetchQuery({
        queryKey: ['forbidden'],
        queryFn: () => Promise.reject(error),
      }),
    ).rejects.toBe(error)

    expect(onForbidden).toHaveBeenCalledWith(error)
  })

  test('mutation の CSRF 以外の 403 で onForbidden を呼ぶ', async () => {
    const onForbidden = vi.fn()
    const queryClient = createAppQueryClient({ onForbidden })
    const error = new ApiError(403, {
      error: { code: 'PERMISSION_DENIED', message: 'Permission denied' },
    })

    await expect(
      queryClient
        .getMutationCache()
        .build(queryClient, {
          mutationFn: () => Promise.reject(error),
        })
        .execute(undefined),
    ).rejects.toBe(error)

    expect(onForbidden).toHaveBeenCalledWith(error)
  })

  test('CSRF_VALIDATION_FAILED の 403 では onForbidden を呼ばない', async () => {
    const onForbidden = vi.fn()
    const queryClient = createAppQueryClient({ onForbidden })

    await expect(
      queryClient.fetchQuery({
        queryKey: ['csrf'],
        queryFn: () =>
          Promise.reject(
            new ApiError(403, {
              error: {
                code: 'CSRF_VALIDATION_FAILED',
                message: 'CSRF validation failed',
              },
            }),
          ),
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(onForbidden).not.toHaveBeenCalled()
  })

  test('401/403 は retry しない', async () => {
    const queryClient = createAppQueryClient()
    const queryFn = vi.fn().mockRejectedValue(new ApiError(401, null))

    await expect(
      queryClient.fetchQuery({
        queryKey: ['no-retry'],
        queryFn,
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(queryFn).toHaveBeenCalledTimes(1)
  })
})
