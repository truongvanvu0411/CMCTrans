export type AppPage =
  | 'dashboard'
  | 'accounts'
  | 'knowledge'
  | 'translated'
  | 'translated-detail'
  | 'translated-editor'
  | 'settings'

export type AppRoute = {
  page: AppPage
  jobId: string | null
}

export function parseHashRoute(hashValue: string): AppRoute {
  const normalized = hashValue.replace(/^#/, '').trim()
  if (!normalized || normalized === 'dashboard') {
    return { page: 'dashboard', jobId: null }
  }
  if (normalized === 'translated') {
    return { page: 'translated', jobId: null }
  }
  if (normalized === 'accounts') {
    return { page: 'accounts', jobId: null }
  }
  if (normalized === 'knowledge') {
    return { page: 'knowledge', jobId: null }
  }
  if (normalized.startsWith('translated/')) {
    const routePath = normalized.slice('translated/'.length).trim()
    if (routePath.endsWith('/editor')) {
      const jobId = routePath.slice(0, -'/editor'.length).trim()
      return {
        page: jobId ? 'translated-editor' : 'translated',
        jobId: jobId || null,
      }
    }
    const jobId = routePath
    return {
      page: jobId ? 'translated-detail' : 'translated',
      jobId: jobId || null,
    }
  }
  if (normalized === 'settings') {
    return { page: 'settings', jobId: null }
  }
  return { page: 'dashboard', jobId: null }
}

export function buildRouteHash(route: AppRoute): string {
  if (route.page === 'translated-editor' && route.jobId) {
    return `#translated/${route.jobId}/editor`
  }
  if (route.page === 'translated-detail' && route.jobId) {
    return `#translated/${route.jobId}`
  }
  if (route.page === 'translated') {
    return '#translated'
  }
  if (route.page === 'accounts') {
    return '#accounts'
  }
  if (route.page === 'knowledge') {
    return '#knowledge'
  }
  if (route.page === 'settings') {
    return '#settings'
  }
  return '#dashboard'
}

export function navigateToRoute(route: AppRoute): void {
  window.location.hash = buildRouteHash(route)
}
