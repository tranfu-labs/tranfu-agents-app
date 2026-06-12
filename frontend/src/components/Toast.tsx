import { useEffect } from 'react'

type Props = {
  message: string
  onDone: () => void
}

export function Toast({ message, onDone }: Props) {
  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(onDone, 2200)
    return () => window.clearTimeout(timer)
  }, [message, onDone])

  return <div className={`toast ${message ? 'show' : ''}`}>{message}</div>
}
