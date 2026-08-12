import i18n from './i18n/i18n'

export class ApiError extends Error {
  status: number
  body: unknown
  code: string | null
  detail: string | null
  details: Array<unknown>
  retryAfterSeconds: number | null

  constructor(status: number, body: unknown, headers: Headers | null = null) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    this.code = extractErrorCode(body)
    this.detail = extractErrorDetail(body)
    this.details = extractErrorDetails(body)
    this.retryAfterSeconds = extractRetryAfterSeconds(headers)
  }
}

export type AccountDeletionOidcReauthProvider = {
  providerId: string
  displayName: string
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
  CSRF_VALIDATION_FAILED: 'apiError.csrf',
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
    error.code !== 'ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED'
  ) {
    return []
  }

  return error.details.flatMap((detail) => {
    if (!isRecord(detail)) {
      return []
    }
    const { providerId, displayName } = detail
    if (typeof providerId !== 'string' || typeof displayName !== 'string') {
      return []
    }
    return [{ providerId, displayName }]
  })
}

function extractErrorCode(body: unknown): string | null {
  const envelope = extractErrorEnvelope(body)
  const code = envelope?.code

  return typeof code === 'string' ? code : null
}

function extractErrorDetail(body: unknown): string | null {
  const envelope = extractErrorEnvelope(body)
  const envelopeMessage = envelope?.message

  if (typeof envelopeMessage === 'string') {
    return envelopeMessage
  }

  if (!isRecord(body)) {
    return null
  }

  const detail = body.detail
  if (typeof detail === 'string') {
    return detail
  }

  const message = body.message
  return typeof message === 'string' ? message : null
}

function extractErrorDetails(body: unknown): Array<unknown> {
  const envelope = extractErrorEnvelope(body)
  const details = envelope?.details

  if (Array.isArray(details)) {
    return details
  }

  if (!isRecord(body)) {
    return []
  }

  return Array.isArray(body.detail) ? body.detail : []
}

function extractErrorEnvelope(body: unknown): Record<string, unknown> | null {
  if (!isRecord(body) || !isRecord(body.error)) {
    return null
  }

  return body.error
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
