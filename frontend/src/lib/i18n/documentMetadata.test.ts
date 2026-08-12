// @vitest-environment jsdom

import { beforeEach, describe, expect, test } from 'vitest'

import i18n from './i18n'
import { syncDocumentMetadata } from './documentMetadata'

describe('documentMetadata', () => {
  beforeEach(() => {
    document.head.innerHTML = ''
  })

  test('document lang, title, and description follow current route and language', async () => {
    await i18n.changeLanguage('en')

    syncDocumentMetadata('/en/login')

    expect(document.documentElement.lang).toBe('en')
    expect(document.title).toBe('Log in | python-react-template')
    expect(
      document
        .querySelector('meta[name="description"]')
        ?.getAttribute('content'),
    ).toBe('Log in to python-react-template.')
  })

  test('unknown route falls back to common metadata and leaves social meta out of scope', async () => {
    await i18n.changeLanguage('ja')

    syncDocumentMetadata('/missing')

    expect(document.title).toBe('python-react-template')
    expect(document.querySelector('meta[property="og:title"]')).toBeNull()
    expect(document.querySelector('meta[name="twitter:title"]')).toBeNull()
  })
})
