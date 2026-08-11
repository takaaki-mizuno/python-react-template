import { apiClient } from './apiClient'

export type AdminUserListItem = {
  id: string
  email: string
  isActive: boolean
  createdAt: string
  updatedAt: string
  lastLoginAt: string | null
  roles: Array<string>
}

export type AdminUser = AdminUserListItem & {
  permissions: Array<string>
}

export type AdminRole = {
  code: string
  displayName: string
  description?: string | null
  permissions: Array<string>
}

export type AdminUserListParams = {
  offset: number
  limit: number
  search?: string
  isActive?: boolean
  role?: string
}

export type AdminUserListResponse = {
  items: Array<AdminUserListItem>
  total: number
  offset: number
  limit: number
}

export type AdminUserCreatePayload = {
  email: string
  password: string
  isActive: boolean
  roles: Array<string>
}

export type AdminUserUpdatePayload = Partial<AdminUserCreatePayload>

type AdminRoleListResponse = {
  roles: Array<AdminRole>
  permissions: Array<unknown>
}

export async function fetchAdminUsers(
  params: AdminUserListParams,
): Promise<AdminUserListResponse> {
  const searchParams = new URLSearchParams()
  searchParams.set('offset', String(params.offset))
  searchParams.set('limit', String(params.limit))
  if (params.search) {
    searchParams.set('search', params.search)
  }
  if (params.isActive !== undefined) {
    searchParams.set('isActive', String(params.isActive))
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
  return response.roles
}

function compactPayload(
  payload: AdminUserUpdatePayload,
): AdminUserUpdatePayload {
  const entries = Object.entries(payload as Record<string, unknown>).filter(
    ([, value]) => value !== undefined,
  )
  return Object.fromEntries(entries) as AdminUserUpdatePayload
}
