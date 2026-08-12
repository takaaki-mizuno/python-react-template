// @vitest-environment jsdom

import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import DocumentI18n from './i18n'
import { syncDocumentMetadata } from './documentMetadata'
import { DocumentMetadataManager } from './DocumentMetadataManager'

let pathname = '/ja/'

vi.mock('@tanstack/react-router', () => ({
  useRouterState: () => pathname,
}))

vi.mock('./documentMetadata', () => ({
  syncDocumentMetadata: vi.fn(),
}))

afterEach(async () => {
  cleanup()
  pathname = '/ja/'
  vi.mocked(syncDocumentMetadata).mockClear()
  await DocumentI18n.changeLanguage('ja')
})

test('DocumentMetadataManager は route 変更と language 変更で metadata を同期する', async () => {
  const { rerender } = render(<DocumentMetadataManager />)

  await waitFor(() => {
    expect(syncDocumentMetadata).toHaveBeenCalledWith('/ja/')
  })

  pathname = '/ja/login'
  rerender(<DocumentMetadataManager />)
  await waitFor(() => {
    expect(syncDocumentMetadata).toHaveBeenCalledWith('/ja/login')
  })

  vi.mocked(syncDocumentMetadata).mockClear()
  await act(async () => {
    await DocumentI18n.changeLanguage('en')
  })
  rerender(<DocumentMetadataManager />)

  await waitFor(() => {
    expect(syncDocumentMetadata).toHaveBeenCalledWith('/ja/login')
  })
})
