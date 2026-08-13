import i18n from './i18n/i18n'

export class ApiError extends Error {
  status: number
  body: unknown
  type: string | null
  title: string | null
  code: string | null
  detail: string | null
  instance: string | null
  errors: Array<unknown>
  retryAfterSeconds: number | null

  constructor(status: number, body: unknown, headers: Headers | null = null) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    this.type = extractStringMember(body, 'type')
    this.title = extractStringMember(body, 'title')
    this.code = extractErrorCode(body)
    this.detail = extractErrorDetail(body)
    this.instance = extractStringMember(body, 'instance')
    this.errors = extractErrorDetails(body)
    this.retryAfterSeconds = extractRetryAfterSeconds(headers)
  }
}

export type AccountDeletionOidcReauthProvider = {
  provider_id: string
  display_name: string
}

type UserMessageOptions = {
  code?: Partial<Record<string, string>>
  status?: Partial<Record<number, string>>
  fallback?: string
}

type BuiltInErrorMessageKey =
  | 'apiError.csrf'
  | 'apiError.status400'
  | 'apiError.status401'
  | 'apiError.status403'
  | 'apiError.status409'
  | 'apiError.status422'
  | 'apiError.status429'
  | 'apiError.fallback'

const builtInCodeMessageKeys: Record<string, BuiltInErrorMessageKey> = {
  csrf_validation_failed: 'apiError.csrf',
}

const builtInStatusMessageKeys: Partial<
  Record<number, BuiltInErrorMessageKey>
> = {
  400: 'apiError.status400',
  401: 'apiError.status401',
  403: 'apiError.status403',
  409: 'apiError.status409',
  422: 'apiError.status422',
  429: 'apiError.status429',
}

const defaultFallbackMessageKey: BuiltInErrorMessageKey = 'apiError.fallback'

export function toUserMessage(
  error: unknown,
  options: UserMessageOptions = {},
): string {
  if (!(error instanceof ApiError)) {
    return options.fallback ?? translateKey(defaultFallbackMessageKey)
  }

  const codeOverride = error.code ? options.code?.[error.code] : undefined
  if (codeOverride) {
    return codeOverride
  }

  const statusOverride = options.status?.[error.status]
  if (statusOverride) {
    return statusOverride
  }

  const codeMessageKey = error.code
    ? builtInCodeMessageKeys[error.code]
    : undefined
  if (codeMessageKey) {
    return translateKey(codeMessageKey)
  }

  const statusMessageKey = builtInStatusMessageKeys[error.status]
  return (
    (statusMessageKey ? translateKey(statusMessageKey) : undefined) ??
    options.fallback ??
    translateKey(defaultFallbackMessageKey)
  )
}

function translateKey(key: BuiltInErrorMessageKey): string {
  return i18n.t(key)
}

export function accountDeletionOidcReauthProviders(
  error: unknown,
): Array<AccountDeletionOidcReauthProvider> {
  if (
    !(error instanceof ApiError) ||
    error.code !== 'account_deletion_oidc_reauth_required'
  ) {
    return []
  }

  if (!isRecord(error.body) || !Array.isArray(error.body.providers)) {
    return []
  }

  return error.body.providers.flatMap((provider) => {
    if (!isRecord(provider)) {
      return []
    }
    const { provider_id, display_name } = provider
    if (typeof provider_id !== 'string' || typeof display_name !== 'string') {
      return []
    }
    return [{ provider_id, display_name }]
  })
}

function extractErrorCode(body: unknown): string | null {
  const code = extractStringMember(body, 'code')

  return typeof code === 'string' ? code : null
}

function extractErrorDetail(body: unknown): string | null {
  return extractStringMember(body, 'detail')
}

function extractErrorDetails(body: unknown): Array<unknown> {
  if (!isRecord(body)) {
    return []
  }

  return Array.isArray(body.errors) ? body.errors : []
}

function extractStringMember(body: unknown, key: string): string | null {
  if (!isRecord(body)) {
    return null
  }
  const value = body[key]
  return typeof value === 'string' ? value : null
}

function extractRetryAfterSeconds(headers: Headers | null): number | null {
  const retryAfter = headers?.get('Retry-After')
  if (!retryAfter || !/^\d+$/.test(retryAfter)) {
    return null
  }

  const seconds = Number(retryAfter)
  return Number.isSafeInteger(seconds) ? seconds : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
