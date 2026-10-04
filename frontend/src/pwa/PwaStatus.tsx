import { useRegisterSW } from 'virtual:pwa-register/react'

/** Registers the service worker and shows "ready offline" / "update available" notices. */
export function PwaStatus() {
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  if (!offlineReady && !needRefresh) return null

  const close = () => {
    setOfflineReady(false)
    setNeedRefresh(false)
  }

  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-20 mx-auto flex max-w-md items-center gap-3 rounded-2xl bg-forest-950 px-4 py-3 text-sm text-white shadow-raised"
    >
      <p className="flex-1">
        {needRefresh ? 'A new version of the app is available.' : 'The app is ready to work offline.'}
      </p>
      {needRefresh && (
        <button
          type="button"
          onClick={() => void updateServiceWorker()}
          className="rounded-lg bg-white px-3 py-1.5 font-semibold text-forest-900 transition hover:bg-sand-100"
        >
          Update
        </button>
      )}
      <button
        type="button"
        onClick={close}
        className="rounded-lg px-2 py-1.5 text-forest-200 transition hover:text-white"
      >
        Close
      </button>
    </div>
  )
}
