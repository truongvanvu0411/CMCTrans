import { useEffect, useState } from 'react'

import { fetchAccounts, fetchActivity } from '../../api'
import type {
  ActivityFilters,
  ActivityListResponse,
  UserAccount,
} from '../../types'
import { ActivityLogPanel } from './ActivityLogPanel'

const DEFAULT_ACTIVITY_FILTERS: ActivityFilters = {
  userId: '',
  actionType: '',
  targetType: '',
  query: '',
  dateFrom: '',
  dateTo: '',
}

type SystemSettingsPageProps = {
  currentUser: UserAccount
  onShowToast: (message: string, tone?: 'error' | 'success' | 'info') => void
}

export function SystemSettingsPage({
  currentUser,
  onShowToast,
}: SystemSettingsPageProps) {
  const [accounts, setAccounts] = useState<UserAccount[]>([])
  const [activityResponse, setActivityResponse] = useState<ActivityListResponse>({
    items: [],
    total: 0,
    action_types: [],
    target_types: [],
  })
  const [activityFilters, setActivityFilters] = useState<ActivityFilters>(DEFAULT_ACTIVITY_FILTERS)
  const [activityBusy, setActivityBusy] = useState(false)

  async function refreshAccounts() {
    setAccounts(
      await fetchAccounts({
        query: '',
        role: '',
        isActive: 'all',
      }),
    )
  }

  async function refreshActivity(nextFilters: ActivityFilters = activityFilters) {
    setActivityBusy(true)
    try {
      const nextActivity = await fetchActivity(nextFilters)
      setActivityResponse(nextActivity)
    } finally {
      setActivityBusy(false)
    }
  }

  useEffect(() => {
    void refreshAccounts().catch((error) => {
      onShowToast(error instanceof Error ? error.message : 'Could not load accounts.')
    })
    void refreshActivity().catch((error) => {
      onShowToast(error instanceof Error ? error.message : 'Could not load activity.')
    })
    // Filters are applied manually.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section id="settings">
      <header className="topbar">
        <div>
          <h1>System Setting</h1>
          <p>Admin-only access to system visibility, runtime checks, and user activity review.</p>
        </div>
      </header>

      <div className="summary-card-grid">
        <section className="summary-card">
          <span>Activity rows</span>
          <strong>{activityResponse.total}</strong>
          <p>matching current filters</p>
        </section>
        <section className="summary-card">
          <span>Visible users</span>
          <strong>{accounts.length}</strong>
          <p>available in activity filters</p>
        </section>
        <section className="summary-card">
          <span>Current admin</span>
          <strong>{currentUser.username}</strong>
          <p>current operator</p>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <p className="eyebrow">Runtime</p>
          <h2>System overview</h2>
        </div>
        <p className="hint">
          Knowledge Base, Account Management, and Activity Log are shared admin tools. Account CRUD
          now lives in its own dedicated screen.
        </p>
      </section>

      <ActivityLogPanel
        entries={activityResponse.items}
        total={activityResponse.total}
        actionTypes={activityResponse.action_types}
        targetTypes={activityResponse.target_types}
        users={accounts}
        filters={activityFilters}
        busy={activityBusy}
        onFilterChange={setActivityFilters}
        onRefresh={async () => {
          try {
            await refreshActivity()
          } catch (error) {
            onShowToast(error instanceof Error ? error.message : 'Could not load activity.')
          }
        }}
      />
    </section>
  )
}
