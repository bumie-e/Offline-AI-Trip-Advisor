import type { Verdict } from '../api/types'

// Advisory wording only: the verdict reflects reports and forecasts, never a safety promise.
const VERDICT_STYLE: Record<
  Verdict,
  { label: string; icon: string; caption: string; banner: string; iconBg: string; pill: string }
> = {
  go: {
    label: 'GO',
    icon: '✓',
    caption: 'No issues were flagged for your dates in the reports and forecasts checked.',
    banner: 'bg-green-700 text-white',
    iconBg: 'bg-white/20',
    pill: 'bg-green-100 text-green-900 ring-green-200',
  },
  go_with_changes: {
    label: 'GO WITH CHANGES',
    icon: '!',
    caption: 'Reports suggest adjusting your plans. See the reasons below.',
    banner: 'bg-amber-500 text-stone-950',
    iconBg: 'bg-stone-950/10',
    pill: 'bg-amber-100 text-amber-900 ring-amber-200',
  },
  not_advised: {
    label: 'NOT ADVISED',
    icon: '✕',
    caption: 'Reports suggest these dates may be difficult. Consider the alternatives below.',
    banner: 'bg-red-700 text-white',
    iconBg: 'bg-white/20',
    pill: 'bg-red-100 text-red-900 ring-red-200',
  },
}

export function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLE[verdict]
  return (
    <div className={`relative overflow-hidden rounded-2xl px-5 py-6 shadow-raised ${style.banner}`}>
      {/* A faint ring motif, so the colour block does not read as flat. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-16 -right-16 size-48 rounded-full border-[28px] border-current opacity-[0.07]"
      />
      <p className="eyebrow opacity-80">Our verdict for your dates</p>
      <div className="mt-3 flex items-center gap-4">
        <span
          aria-hidden
          className={`flex size-14 shrink-0 items-center justify-center rounded-2xl text-3xl font-black ${style.iconBg}`}
        >
          {style.icon}
        </span>
        <p className="text-[2.1rem] leading-[1.05] font-black tracking-tight sm:text-5xl">
          {style.label}
        </p>
      </div>
      <p className="mt-4 max-w-md text-[15px] leading-snug font-medium opacity-95">{style.caption}</p>
    </div>
  )
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLE[verdict]
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold tracking-wide ring-1 ${style.pill}`}
    >
      {style.label}
    </span>
  )
}
