import { queryOptions } from '@tanstack/react-query'

import { ApiError } from './apiError'
import { apiClient } from './apiClient'
import { queryKeys } from './queryKeys'

export type AuthUser = {
  id: string
  email: string
  roles: Array<string>
  permissions: Array<string>
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

export type OidcProvider = {
  providerId: string
  displayName: string
}

type OidcProvidersResponse = {
  providers: Array<OidcProvider>
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

export async function fetchOidcProviders(): Promise<Array<OidcProvider>> {
  const response = await apiClient.get<OidcProvidersResponse>(
    '/api/auth/oidc/providers',
  )
  return Array.isArray(response.providers) ? response.providers : []
}

export function startOidcLogin(
  providerId: string,
  redirect: string,
  assign: (url: string) => void = window.location.assign.bind(window.location),
) {
  assign(oidcStartUrl(providerId, 'start', redirect))
}

export function startOidcReauth(
  providerId: string,
  redirect: string,
  assign: (url: string) => void = window.location.assign.bind(window.location),
) {
  assign(oidcStartUrl(providerId, 'reauth', redirect))
}

function oidcStartUrl(
  providerId: string,
  action: 'start' | 'reauth',
  redirect: string,
) {
  const params = new URLSearchParams({ redirect })
  return `/api/auth/oidc/${encodeURIComponent(providerId)}/${action}?${params.toString()}`
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
