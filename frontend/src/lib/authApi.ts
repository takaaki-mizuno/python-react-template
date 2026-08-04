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

export type RegisterPayload = {
  email: string
  password: string
}

export type DeleteAccountPayload = {
  confirmEmail: string
  password?: string
}

export async function fetchCurrentUserOrNull(options?: {
  signal?: AbortSignal
}): Promise<AuthUser | null> {
  try {
    return await apiClient.get<AuthUser>('/api/auth/me', {
      signal: options?.signal,
    })
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
  return apiClient.post<AuthUser>('/api/auth/login', { body: payload })
}

export async function registerWithPassword(
  payload: RegisterPayload,
): Promise<AuthUser> {
  return apiClient.post<AuthUser>('/api/auth/register', { body: payload })
}

export async function logoutCurrentSession(): Promise<void> {
  return apiClient.post<void>('/api/auth/logout')
}

export async function deleteCurrentAccount(
  payload: DeleteAccountPayload,
): Promise<void> {
  return apiClient.delete<void>('/api/auth/me', { body: payload })
}

export function currentUserQueryOptions() {
  return queryOptions({
    queryKey: queryKeys.auth.me,
    queryFn: ({ signal }) => fetchCurrentUserOrNull({ signal }),
    retry: false,
    staleTime: 0,
    refetchOnMount: false,
  })
}
