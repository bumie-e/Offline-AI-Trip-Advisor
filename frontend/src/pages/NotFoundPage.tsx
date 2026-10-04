import { Link } from 'react-router'
import { CompassIcon } from '../components/icons'

export function NotFoundPage() {
  return (
    <section className="card mt-4 flex flex-col items-center px-6 py-10 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-sand-100 text-forest-800">
        <CompassIcon className="size-6" />
      </span>
      <h1 className="mt-4 font-display text-2xl font-semibold text-stone-900">Page not found</h1>
      <Link to="/" className="btn-primary mt-6">
        Back to places
      </Link>
    </section>
  )
}
