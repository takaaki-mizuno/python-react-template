export type AuthFormFeedbackProps = {
  id: string
  message: string | null
}

export function AuthFormFeedback({ id, message }: AuthFormFeedbackProps) {
  if (!message) {
    return null
  }

  return (
    <p className="text-sm text-red-600" id={id} role="alert">
      {message}
    </p>
  )
}
