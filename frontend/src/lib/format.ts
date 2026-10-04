import type { IsoDate, IsoDateTime, TravelMode } from '../api/types'

/** `YYYY-MM-DD` as a local date, so it never shifts a day across time zones. */
function parseIsoDate(value: IsoDate): Date {
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Today (plus an offset) as a local `YYYY-MM-DD`, the format of `<input type="date">`. */
export function todayIso(offsetDays = 0): IsoDate {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const dayMonth = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })
const dayMonthYear = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})
const dateTime = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDate(value: IsoDate, withYear = true): string {
  return (withYear ? dayMonthYear : dayMonth).format(parseIsoDate(value))
}

export function formatDateTime(value: IsoDateTime): string {
  return dateTime.format(new Date(value))
}

/** "14 Oct 2026", "14–16 Oct 2026" or "30 Oct – 2 Nov 2026". */
export function formatDateRange(start: IsoDate, end: IsoDate): string {
  if (start === end) return formatDate(start)
  const a = parseIsoDate(start)
  const b = parseIsoDate(end)
  if (a.getFullYear() !== b.getFullYear()) return `${formatDate(start)} – ${formatDate(end)}`
  if (a.getMonth() === b.getMonth()) return `${a.getDate()}–${formatDate(end)}`
  return `${formatDate(start, false)} – ${formatDate(end)}`
}

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  if (!h) return `${m} min`
  return m ? `${h} h ${m} min` : `${h} h`
}

/** "today", "1 day old", "13 days old". */
export function ageLabel(value: IsoDate | IsoDateTime): string {
  const days = Math.round(
    (parseIsoDate(todayIso()).getTime() - parseIsoDate(value).getTime()) / 86_400_000,
  )
  if (days <= 0) return 'today'
  return days === 1 ? '1 day old' : `${days} days old`
}

export function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`
}

/** Fallback when the place name is not known: "olumo-rock" -> "Olumo Rock". */
export function siteNameFromId(siteId: string): string {
  return siteId
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export const MODE_LABEL: Record<TravelMode, string> = {
  road: 'By road',
  train: 'By train',
  flight: 'By air',
  walk: 'On foot',
}
