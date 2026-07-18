import { ApiError } from './apiError'
import { readCookie } from './cookies'

let csrfBootstrapPromise: Promise<void> | null = null

async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const body = await response
    .clone()
    .json()
    .catch(() => null)
  return new ApiError(response.status, body)
}

async function ensureCsrfToken(): Promise<void> {
  if (!csrfBootstrapPromise) {
    csrfBootstrapPromise = fetch('/api/auth/csrf', {
      credentials: 'include',
    })
      .then(async (response) => {
        if (!response.ok) {
          throw await apiErrorFromResponse(response)
        }
      })
      .finally(() => {
        csrfBootstrapPromise = null
      })
  }

  await csrfBootstrapPromise
}

async function request<T>(input: string, init: RequestInit = {}): Promise<T> {
  const headers = headersToObject(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()
  const isUnsafeMethod = !['GET', 'HEAD'].includes(method)

  if (isUnsafeMethod) {
    await ensureCsrfToken()
    const csrfToken = readCookie('csrf_token')
    if (!csrfToken) {
      throw new Error('Missing csrf_token cookie after bootstrap')
    }
    headers['X-CSRF-Token'] = csrfToken
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

function headersToObject(headersInit: HeadersInit | undefined) {
  const headers: Record<string, string> = {}
  new Headers(headersInit).forEach((value, key) => {
    headers[key] = value
  })
  return headers
}

export const apiClient = {
  get: <T>(input: string) => request<T>(input),
  post: <T>(input: string, body?: unknown) =>
    request<T>(input, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
}
