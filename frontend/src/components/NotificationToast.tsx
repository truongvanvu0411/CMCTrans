type NotificationToastProps = {
  message: string
  tone: 'error' | 'success' | 'info'
  onDismiss: () => void
}

export function NotificationToast({
  message,
  tone,
  onDismiss,
}: NotificationToastProps) {
  return (
    <div className={`toast-banner ${tone}`} role="status" aria-live="polite">
      <p>{message}</p>
      <button type="button" className="toast-dismiss-button" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  )
}
