import { Alert, AlertDescription } from '@/components/atoms/alert'

export type AuthFormFeedbackProps = {
  id: string
  message: string | null
}

export function AuthFormFeedback({ id, message }: AuthFormFeedbackProps) {
  if (!message) {
    return null
  }

  return (
    <Alert id={id} variant="destructive">
      <AlertDescription className="text-destructive!">
        {message}
      </AlertDescription>
    </Alert>
  )
}
