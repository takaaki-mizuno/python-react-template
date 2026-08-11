import { AlertTriangle } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/atoms/alert'
import { Button } from '@/components/atoms/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/atoms/dialog'

type AdminConfirmDialogProps = {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  errorMessage?: string | null
  isPending?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function AdminConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  errorMessage = null,
  isPending = false,
  onCancel,
  onConfirm,
}: AdminConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !isPending) {
          onCancel()
        }
      }}
    >
      <DialogContent className="w-full max-w-md gap-5" showCloseButton={false}>
        <div className="grid gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-destructive" />
            <DialogTitle>{title}</DialogTitle>
          </div>
          <DialogDescription>{description}</DialogDescription>
        </div>
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button
            disabled={isPending}
            type="button"
            variant="outline"
            onClick={onCancel}
          >
            キャンセル
          </Button>
          <Button
            disabled={isPending}
            type="button"
            variant="destructive"
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
