import { describe, expect, test } from 'vitest'

import { hasAnyPermission, hasPermission } from './permissions'
import type { AuthUser } from './authApi'

describe('permissions', () => {
  test('permission の有無を判定する', () => {
    const user: AuthUser = {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'admin@example.com',
      languageCode: 'ja',
      roles: ['admin'],
      permissions: ['admin:access'],
    }

    expect(hasPermission(user, 'admin:access')).toBe(true)
    expect(hasPermission(user, 'users:write')).toBe(false)
    expect(hasAnyPermission(user, ['users:write', 'admin:access'])).toBe(true)
  })

  test('null user は権限なしとして扱う', () => {
    expect(hasPermission(null, 'admin:access')).toBe(false)
    expect(hasAnyPermission(undefined, ['admin:access'])).toBe(false)
    expect(hasAnyPermission(null, [])).toBe(false)
  })
})
