import type { Citation } from '../lib/citations'
import { ChevronRightIcon, ExternalIcon } from './icons'

/** The sources behind one piece of advice, collapsed by default to keep the page short. */
export function Sources({ ids, resolve }: { ids?: string[]; resolve: (id: string) => Citation }) {
  if (!ids?.length) return null
  const citations = ids.map(resolve)

  return (
    <details className="group mt-3 text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-md text-xs font-medium text-stone-500 transition-colors select-none hover:text-stone-800 [&::-webkit-details-marker]:hidden">
        <ChevronRightIcon className="size-3.5 transition-transform group-open:rotate-90" />
        {citations.length} source{citations.length === 1 ? '' : 's'}:{' '}
        {[...new Set(citations.map((c) => c.label))].slice(0, 2).join(', ')}
        {citations.length > 2 && '…'}
      </summary>
      <ul className="mt-2 space-y-2.5 border-l-2 border-sand-200 pl-3">
        {citations.map((c) => (
          <li key={c.id}>
            <SourceLine citation={c} />
          </li>
        ))}
      </ul>
    </details>
  )
}

/** One source: publisher (linked), date and age, what it says, and its ID. */
export function SourceLine({ citation: c }: { citation: Citation }) {
  return (
    <div className="text-sm">
      <p className="font-medium text-stone-800">
        {c.url ? (
          <a
            href={c.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 underline decoration-stone-300 underline-offset-2 transition-colors hover:decoration-stone-600"
          >
            {c.label}
            <ExternalIcon className="size-3 text-stone-400" />
          </a>
        ) : (
          c.label
        )}
        {c.when && <span className="font-normal text-stone-500"> · {c.when}</span>}
      </p>
      {c.detail && <p className="mt-0.5 leading-snug text-stone-600">{c.detail}</p>}
      <p className="mt-0.5 font-mono text-[10.5px] break-all text-stone-400">{c.id}</p>
    </div>
  )
}
