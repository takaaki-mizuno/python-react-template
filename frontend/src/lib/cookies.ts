export function readCookie(name: string): string | null {
  const prefix = `${name}=`

  for (const item of document.cookie.split(';')) {
    const trimmed = item.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }

  return null
}
