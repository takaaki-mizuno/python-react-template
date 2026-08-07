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

const builtInCodeMessages: Record<string, string> = {
  CSRF_VALIDATION_FAILED:
    'セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。',
}

const builtInStatusMessages: Partial<Record<number, string>> = {
  400: '入力内容を確認してください。',
  401: 'ログインが必要です。',
  403: 'この操作を実行する権限がありません。',
  409: '現在の状態では処理できません。',
  422: '入力内容を確認してください。',
  429: '試行回数が多すぎます。時間をおいて再度お試しください。',
}

const defaultFallbackMessage =
  '通信に失敗しました。時間をおいて再度お試しください。'

export function toUserMessage(
  error: unknown,
  options: UserMessageOptions = {},
): string {
  if (!(error instanceof ApiError)) {
    return options.fallback ?? defaultFallbackMessage
  }

  const codeOverride = error.code ? options.code?.[error.code] : undefined
  if (codeOverride) {
    return codeOverride
  }

  const statusOverride = options.status?.[error.status]
  if (statusOverride) {
    return statusOverride
  }

  if (error.code && builtInCodeMessages[error.code]) {
    return builtInCodeMessages[error.code]
  }

  return (
    builtInStatusMessages[error.status] ??
    options.fallback ??
    defaultFallbackMessage
  )
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
