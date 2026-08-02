import { Input } from '@/components/atoms/input'

type AuthTextFieldProps = {
  autoComplete: string
  describedBy?: string
  id: string
  invalid?: boolean
  label: string
  onChange: (value: string) => void
  required?: boolean
  type: 'email' | 'password' | 'text'
  value: string
}

export function AuthTextField({
  autoComplete,
  describedBy,
  id,
  invalid = false,
  label,
  onChange,
  required = false,
  type,
  value,
}: AuthTextFieldProps) {
  return (
    <div className="grid gap-2">
      <label className="text-sm font-medium text-landing-ink" htmlFor={id}>
        {label}
      </label>
      <Input
        aria-describedby={describedBy}
        aria-invalid={invalid ? true : undefined}
        autoComplete={autoComplete}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        type={type}
        value={value}
      />
    </div>
  )
}
