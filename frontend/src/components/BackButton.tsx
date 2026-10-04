import { useLocation, useNavigate } from 'react-router'

/** Goes back in history, or to `fallback` when the page was opened directly. */
export function BackButton({ fallback, label = 'Back' }: { fallback: string; label?: string }) {
  const navigate = useNavigate()
  const location = useLocation()
  const hasHistory = location.key !== 'default'

  return (
    <button
      type="button"
      onClick={() => (hasHistory ? navigate(-1) : navigate(fallback))}
      className="-ml-2 inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm font-medium text-green-800 active:bg-green-50"
    >
      <span aria-hidden>←</span> {label}
    </button>
  )
}
