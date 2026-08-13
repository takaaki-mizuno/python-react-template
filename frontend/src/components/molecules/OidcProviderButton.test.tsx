// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import { OidcProviderButton } from './OidcProviderButton'

test('OidcProviderButton は provider display name を表示し click handler を呼ぶ', () => {
  const onClick = vi.fn()

  render(
    <OidcProviderButton
      onClick={onClick}
      provider={{ provider_id: 'google', display_name: 'Google' }}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Googleで続行' }))

  expect(onClick).toHaveBeenCalledTimes(1)
})
