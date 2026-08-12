import { readFileSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, test } from 'vitest'

const sourceRoot = join(process.cwd(), 'src')
const japanesePattern = /[ぁ-んァ-ヶ一-龥]/
const allowedFiles = new Set([
  // Language names are deliberately shown in their native language.
  'lib/i18n/languages.ts',
])

describe('hardcoded Japanese scan', () => {
  test('UI source strings live in locale JSON files', () => {
    const offenders = sourceFiles(sourceRoot).filter((file) => {
      const path = relative(sourceRoot, file)
      if (
        path.includes('/locales/') ||
        path.endsWith('.test.ts') ||
        path.endsWith('.test.tsx') ||
        path === 'routeTree.gen.ts' ||
        allowedFiles.has(path)
      ) {
        return false
      }

      return japanesePattern.test(readFileSync(file, 'utf8'))
    })

    expect(offenders.map((file) => relative(sourceRoot, file))).toEqual([])
  })
})

function sourceFiles(directory: string): Array<string> {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      return sourceFiles(path)
    }
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : []
  })
}
