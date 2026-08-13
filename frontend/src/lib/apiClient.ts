import { ApiError } from './apiError'
import { readCookie } from './cookies'

let csrfBootstrapPromise: Promise<void> | null = null

export type ApiRequestOptions = {
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
}

type InternalRequestOptions = ApiRequestOptions & {
  method?: string
}

async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const body = await response
    .clone()
    .json()
    .catch(() => null)
  return new ApiError(response.status, body, response.headers)
}

async function bootstrapCsrfToken(
  options: { force?: boolean } = {},
): Promise<void> {
  if (options.force) {
    csrfBootstrapPromise = null
  }

  if (!csrfBootstrapPromise) {
    csrfBootstrapPromise = fetch('/api/auth/csrf', {
      credentials: 'include',
    }).then(async (response) => {
      if (!response.ok) {
        throw await apiErrorFromResponse(response)
      }
    })
  }

  const activeBootstrap = csrfBootstrapPromise
  try {
    await activeBootstrap
  } finally {
    if (csrfBootstrapPromise === activeBootstrap) {
      csrfBootstrapPromise = null
    }
  }
}

async function ensureCsrfToken(): Promise<void> {
  if (!readCookie('csrf_token')) {
    await bootstrapCsrfToken()
  }
}

async function request<T>(
  input: string,
  options: InternalRequestOptions = {},
  hasRetriedCsrf = false,
): Promise<T> {
  const { body, headers: headersInit, signal } = options
  const headers = new Headers(headersInit)
  const method = (options.method ?? 'GET').toUpperCase()
  const isUnsafeMethod = !['GET', 'HEAD'].includes(method)

  if (isUnsafeMethod) {
    await ensureCsrfToken()
    const csrfToken = readCookie('csrf_token')
    if (!csrfToken) {
      throw new Error('Missing csrf_token cookie after bootstrap')
    }
    headers.set('X-CSRF-Token', csrfToken)
    if (body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
  }

  const init: RequestInit = {
    method,
    headers,
    credentials: 'include',
    signal,
  }

  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }

  const response = await fetch(input, {
    ...init,
  })

  if (!response.ok) {
    const error = await apiErrorFromResponse(response)
    if (
      isUnsafeMethod &&
      !hasRetriedCsrf &&
      error.status === 403 &&
      error.code === 'csrf_validation_failed'
    ) {
      await bootstrapCsrfToken({ force: true })
      return request<T>(input, options, true)
    }

    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(input: string, options?: Omit<ApiRequestOptions, 'body'>) =>
    request<T>(input, options),
  post: <T>(input: string, options?: ApiRequestOptions) =>
    request<T>(input, { ...options, method: 'POST' }),
  put: <T>(input: string, options?: ApiRequestOptions) =>
    request<T>(input, { ...options, method: 'PUT' }),
  patch: <T>(input: string, options?: ApiRequestOptions) =>
    request<T>(input, { ...options, method: 'PATCH' }),
  delete: <T>(input: string, options?: ApiRequestOptions) =>
    request<T>(input, { ...options, method: 'DELETE' }),
}
