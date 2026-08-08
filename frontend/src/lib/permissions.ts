import type { AuthUser } from './authApi'

export function hasPermission(
  user: AuthUser | null | undefined,
  permission: string,
): boolean {
  return (
    Array.isArray(user?.permissions) && user.permissions.includes(permission)
  )
}

export function hasAnyPermission(
  user: AuthUser | null | undefined,
  permissions: Iterable<string>,
): boolean {
  for (const permission of permissions) {
    if (hasPermission(user, permission)) {
      return true
    }
  }
  return false
}
