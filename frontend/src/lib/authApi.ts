import { queryOptions } from '@tanstack/react-query'

import { ApiError } from './apiError'
import { apiClient } from './apiClient'
import { queryKeys } from './queryKeys'

export type AuthUser = {
  id: string
  email: string
}

export type LoginPayload = {
  email: string
  password: string
}

export async function fetchCurrentUserStrict(): Promise<AuthUser> {
  return apiClient.get<AuthUser>('/api/auth/me')
}

export async function fetchCurrentUserOrNull(): Promise<AuthUser | null> {
  try {
    return await fetchCurrentUserStrict()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null
    }
    throw error
  }
}

export async function loginWithPassword(
  payload: LoginPayload,
): Promise<AuthUser> {
  return apiClient.post<AuthUser>('/api/auth/login', payload)
}

export async function logoutCurrentSession(): Promise<void> {
  return apiClient.post<void>('/api/auth/logout')
}

export function currentUserQueryOptions() {
  return queryOptions({
    queryKey: queryKeys.auth.me,
    queryFn: fetchCurrentUserOrNull,
    retry: false,
  })
}

export function currentUserStrictQueryOptions() {
  return queryOptions({
    queryKey: queryKeys.auth.strictMe,
    queryFn: fetchCurrentUserStrict,
    retry: false,
  })
}
