import type { Citation } from '../lib/citations'

/** The sources behind one piece of advice, collapsed by default to keep the page short. */
export function Sources({ ids, resolve }: { ids?: string[]; resolve: (id: string) => Citation }) {
  if (!ids?.length) return null
  const citations = ids.map(resolve)

  return (
    <details className="group mt-3 text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-md text-xs font-medium text-stone-500 select-none [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="transition-transform group-open:rotate-90">
          ›
        </span>
        {citations.length} source{citations.length === 1 ? '' : 's'}:{' '}
        {[...new Set(citations.map((c) => c.label))].slice(0, 2).join(', ')}
        {citations.length > 2 && '…'}
      </summary>
      <ul className="mt-2 space-y-2 border-l-2 border-stone-200 pl-3">
        {citations.map((c) => (
          <li key={c.id}>
            <p className="font-medium text-stone-800">
              {c.url ? (
                <a href={c.url} target="_blank" rel="noreferrer" className="underline decoration-stone-300 underline-offset-2">
                  {c.label}
                </a>
              ) : (
                c.label
              )}
              {c.when && <span className="font-normal text-stone-500"> · {c.when}</span>}
            </p>
            {c.detail && <p className="text-stone-600">{c.detail}</p>}
            <p className="font-mono text-[11px] break-all text-stone-400">{c.id}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}
