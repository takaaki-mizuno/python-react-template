import type { OidcProvider } from '@/lib/authApi'
import { Button } from '@/components/atoms/button'

type OidcProviderButtonProps = {
  isDisabled?: boolean
  onClick: () => void
  provider: OidcProvider
}

export function OidcProviderButton({
  isDisabled = false,
  onClick,
  provider,
}: OidcProviderButtonProps) {
  return (
    <Button
      className="h-11 w-full justify-center"
      disabled={isDisabled}
      onClick={onClick}
      type="button"
      variant="outline"
    >
      {provider.displayName}で続行
    </Button>
  )
}
