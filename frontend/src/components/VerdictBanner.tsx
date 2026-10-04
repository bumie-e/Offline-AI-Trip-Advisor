import type { Verdict } from '../api/types'

// Advisory wording only: the verdict reflects reports and forecasts, never a safety promise.
const VERDICT_STYLE: Record<Verdict, { label: string; icon: string; caption: string; banner: string; pill: string }> = {
  go: {
    label: 'GO',
    icon: '✓',
    caption: 'No issues were flagged for your dates in the reports and forecasts checked.',
    banner: 'bg-green-700 text-white',
    pill: 'bg-green-100 text-green-900',
  },
  go_with_changes: {
    label: 'GO WITH CHANGES',
    icon: '!',
    caption: 'Reports suggest adjusting your plans. See the reasons below.',
    banner: 'bg-amber-500 text-stone-950',
    pill: 'bg-amber-100 text-amber-900',
  },
  not_advised: {
    label: 'NOT ADVISED',
    icon: '✕',
    caption: 'Reports suggest these dates may be difficult. Consider the alternatives below.',
    banner: 'bg-red-700 text-white',
    pill: 'bg-red-100 text-red-900',
  },
}

export function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLE[verdict]
  return (
    <div className={`flex items-start gap-4 rounded-3xl px-5 py-6 shadow-lg ${style.banner}`}>
      <span
        aria-hidden
        className="flex size-12 shrink-0 items-center justify-center rounded-full bg-black/15 text-2xl font-black"
      >
        {style.icon}
      </span>
      <div>
        <p className="text-xs font-bold tracking-widest uppercase opacity-80">Verdict</p>
        <p className="mt-0.5 text-4xl leading-none font-black tracking-tight">{style.label}</p>
        <p className="mt-3 text-[15px] leading-snug font-medium">{style.caption}</p>
      </div>
    </div>
  )
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLE[verdict]
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold tracking-wide ${style.pill}`}>
      {style.label}
    </span>
  )
}
