const authPagePaths = new Set(['/login', '/register'])

export function normalizeRedirectHref(
  value: unknown,
  fallback = '/app',
): string {
  if (typeof value !== 'string' || value.length === 0) {
    return fallback
  }

  if (value.includes('\\') || hasAsciiControl(value)) {
    return fallback
  }

  let url: URL
  try {
    url = new URL(value, window.location.origin)
  } catch {
    return fallback
  }

  if (url.origin !== window.location.origin) {
    return fallback
  }

  if (authPagePaths.has(normalizePathname(url.pathname))) {
    return fallback
  }

  return `${url.pathname}${url.search}${url.hash}`
}

function normalizePathname(pathname: string): string {
  const withoutTrailingSlash = pathname.replace(/\/+$/, '')

  return (withoutTrailingSlash || '/').toLowerCase()
}

function hasAsciiControl(value: string): boolean {
  for (const character of value) {
    const code = character.charCodeAt(0)
    if (code <= 0x1f || code === 0x7f) {
      return true
    }
  }

  return false
}
