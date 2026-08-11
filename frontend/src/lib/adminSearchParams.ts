export type AdminUserSearchParams = {
  offset: number
  search?: string
  isActive?: boolean
  role?: string
}

type RawSearchParams = Record<string, unknown>

export function parseAdminUserSearchParams(
  search: RawSearchParams,
): AdminUserSearchParams {
  return {
    offset: parseOffset(search.offset),
    search: parseNonEmptyString(search.search),
    isActive: parseBoolean(search.isActive),
    role: parseNonEmptyString(search.role),
  }
}

export function serializeAdminUserSearchParams(
  params: AdminUserSearchParams,
): Record<string, string> {
  const serialized: Record<string, string> = {
    offset: String(Math.max(0, params.offset)),
  }
  if (params.search) {
    serialized.search = params.search
  }
  if (params.isActive !== undefined) {
    serialized.isActive = String(params.isActive)
  }
  if (params.role) {
    serialized.role = params.role
  }
  return serialized
}

function parseOffset(value: unknown): number {
  if (typeof value !== 'string' && typeof value !== 'number') {
    return 0
  }
  const offset = Number(value)
  return Number.isSafeInteger(offset) && offset >= 0 ? offset : 0
}

function parseBoolean(value: unknown): boolean | undefined {
  if (value === true || value === 'true') {
    return true
  }
  if (value === false || value === 'false') {
    return false
  }
  return undefined
}

function parseNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}
