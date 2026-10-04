import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold text-stone-900">Page not found</h1>
      <Link to="/" className="font-medium text-green-800 underline">
        Back to places
      </Link>
    </section>
  )
}
