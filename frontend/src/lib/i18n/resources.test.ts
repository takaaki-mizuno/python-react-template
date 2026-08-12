import { describe, expect, test } from 'vitest'

import { resources } from './resources'

describe('i18n resources', () => {
  test('ja and en have the same namespace and nested key sets', () => {
    expect(Object.keys(resources.ja).sort()).toEqual(
      Object.keys(resources.en).sort(),
    )

    const namespaces = Object.keys(resources.ja) as Array<
      keyof typeof resources.ja
    >

    for (const namespace of namespaces) {
      expect(flattenKeys(resources.ja[namespace]).sort()).toEqual(
        flattenKeys(resources.en[namespace]).sort(),
      )
    }
  })
})

function flattenKeys(value: unknown, prefix = ''): Array<string> {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) =>
      flattenKeys(item, `${prefix}[${index}]`),
    )
  }
  if (typeof value !== 'object' || value === null) {
    return [prefix]
  }

  return Object.entries(value).flatMap(([key, nested]) =>
    flattenKeys(nested, prefix ? `${prefix}.${key}` : key),
  )
}
