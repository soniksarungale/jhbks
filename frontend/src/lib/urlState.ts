import { useCallback, useSyncExternalStore } from 'react'

// View state lives in the query string so any view can be bookmarked or shared.

function subscribe(cb: () => void) {
  window.addEventListener('popstate', cb)
  return () => window.removeEventListener('popstate', cb)
}

const getSearch = () => window.location.search

export function useUrlParams(): [URLSearchParams, (patch: Record<string, string | null>) => void] {
  const search = useSyncExternalStore(subscribe, getSearch)
  const params = new URLSearchParams(search)

  const update = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(window.location.search)
    for (const [k, v] of Object.entries(patch)) {
      if (v == null) next.delete(k)
      else next.set(k, v)
    }
    window.history.pushState(null, '', `${window.location.pathname}?${next}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, [])

  return [params, update]
}
