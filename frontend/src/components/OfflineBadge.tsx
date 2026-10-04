import { OfflineReadyIcon } from './icons'

/** The one visual for "this trip is stored on the device". */
export function OfflineBadge({
  label = 'Available offline',
  tone = 'light',
}: {
  label?: string
  /** `light` on white or cream, `dark` on the forest header. */
  tone?: 'light' | 'dark'
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
        tone === 'dark'
          ? 'bg-white/12 text-white ring-1 ring-white/25'
          : 'bg-forest-50 text-forest-800 ring-1 ring-forest-200'
      }`}
    >
      <OfflineReadyIcon className="size-3.5" strokeWidth={2.2} />
      {label}
    </span>
  )
}
