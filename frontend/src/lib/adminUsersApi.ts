import { apiClient } from './apiClient'

export type AdminUserListItem = {
  id: string
  email: string
  is_active: boolean
  created_at: number
  updated_at: number
  last_login_at: number | null
  roles: Array<string>
}

export type AdminUser = AdminUserListItem & {
  permissions: Array<string>
}

export type AdminRole = {
  code: string
  display_name: string
  description?: string | null
  permissions: Array<string>
}

export type AdminUserListParams = {
  offset: number
  limit: number
  query?: string
  is_active?: boolean
  role?: string
}

export type AdminUserListResponse = {
  data: Array<AdminUserListItem>
  count: number
  offset: number
  limit: number
}

export type AdminUserCreatePayload = {
  email: string
  password: string
  is_active: boolean
  roles: Array<string>
}

export type AdminUserUpdatePayload = Partial<AdminUserCreatePayload>

type AdminRoleListResponse = {
  data: Array<AdminRole>
  permissions: Array<unknown>
}

export async function fetchAdminUsers(
  params: AdminUserListParams,
): Promise<AdminUserListResponse> {
  const searchParams = new URLSearchParams()
  searchParams.set('offset', String(params.offset))
  searchParams.set('limit', String(params.limit))
  if (params.query) {
    searchParams.set('query', params.query)
  }
  if (params.is_active !== undefined) {
    searchParams.set('is_active', String(params.is_active))
  }
  if (params.role) {
    searchParams.set('role', params.role)
  }
  return apiClient.get<AdminUserListResponse>(
    `/api/admin/users?${searchParams.toString()}`,
  )
}

export async function fetchAdminUser(userId: string): Promise<AdminUser> {
  return apiClient.get<AdminUser>(`/api/admin/users/${userId}`)
}

export async function createAdminUser(
  payload: AdminUserCreatePayload,
): Promise<AdminUser> {
  return apiClient.post<AdminUser>('/api/admin/users', { body: payload })
}

export async function updateAdminUser(
  userId: string,
  payload: AdminUserUpdatePayload,
): Promise<AdminUser> {
  return apiClient.patch<AdminUser>(`/api/admin/users/${userId}`, {
    body: compactPayload(payload),
  })
}

export async function deleteAdminUser(userId: string): Promise<void> {
  return apiClient.delete<void>(`/api/admin/users/${userId}`)
}

export async function fetchAdminRoles(): Promise<Array<AdminRole>> {
  const response =
    await apiClient.get<AdminRoleListResponse>('/api/admin/roles')
  return response.data
}

function compactPayload(
  payload: AdminUserUpdatePayload,
): AdminUserUpdatePayload {
  const entries = Object.entries(payload as Record<string, unknown>).filter(
    ([, value]) => value !== undefined,
  )
  return Object.fromEntries(entries) as AdminUserUpdatePayload
}
