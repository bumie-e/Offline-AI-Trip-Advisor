import { useLocation, useNavigate } from 'react-router'
import { ArrowLeftIcon } from './icons'

const BACK_LINK_CLASS = {
  dark: 'text-forest-800 hover:bg-forest-50 active:bg-forest-100',
  light: 'text-forest-100 hover:bg-white/10 active:bg-white/15',
}

/** Goes back in history, or to `fallback` when the page was opened directly. */
export function BackButton({
  fallback,
  label = 'Back',
  tone = 'dark',
}: {
  fallback: string
  label?: string
  /** `light` for use on the dark trip header. */
  tone?: 'dark' | 'light'
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const hasHistory = location.key !== 'default'

  return (
    <button
      type="button"
      onClick={() => (hasHistory ? navigate(-1) : navigate(fallback))}
      className={`-ml-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium transition-colors ${BACK_LINK_CLASS[tone]}`}
    >
      <ArrowLeftIcon className="size-4" /> {label}
    </button>
  )
}
