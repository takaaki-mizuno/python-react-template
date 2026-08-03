import { cn } from '@/lib/css'

type AnchorButtonProps = {
  className?: string
  href: string
  label: string
  variant: 'primary' | 'secondary'
}

const AnchorButton = ({
  className,
  href,
  label,
  variant,
}: AnchorButtonProps) => {
  return (
    <a
      className={cn(
        'landing-button',
        variant === 'primary'
          ? 'landing-button-primary'
          : 'landing-button-secondary',
        className,
      )}
      href={href}
    >
      {label}
    </a>
  )
}

export default AnchorButton
